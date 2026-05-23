from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from asr.agents.base import BaseAgent
from asr.agents.llm_tracker import log_token_usage
from asr.agents.opencode_backend import opencode_completion
from asr.config.models import AgentConfig
from asr.events.models import (
    Event,
    EventType,
    AgentName,
    SpecDiffFoundEvent,
    SpecAlignedEvent,
    AnalyzerFeedbackEvent,
    ErrorOccurredEvent,
)
from asr.events.store import EventStore


@dataclass
class AnalysisReport:
    aligned: bool = False
    task_type: str = "bugfix"
    missing_features: list[str] = field(default_factory=list)
    logic_issues: list[str] = field(default_factory=list)
    constraint_violations: list[str] = field(default_factory=list)


class AnalyzerAgent(BaseAgent):
    def __init__(
        self,
        config: AgentConfig,
        event_store: EventStore,
        project_dir: Path,
    ):
        super().__init__(name=AgentName.ANALYZER, event_store=event_store)
        self._config = config
        self._project_dir = project_dir

    async def process(self, event: Event) -> list[Event]:
        if not self.validate_event(event):
            return []

        try:
            if event.type in (EventType.SPEC_DIFF_FOUND, EventType.SPEC_ALIGNED):
                return await self._handle_analysis_request(event)
        except Exception as e:
            return [
                ErrorOccurredEvent(
                    task_id=event.task_id,
                    from_agent=AgentName.ANALYZER,
                    to_agent=AgentName.CONTROLLER,
                    payload={
                        "agent": "analyzer",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "retry_hint": "retryable",
                    },
                )
            ]

        return []

    async def _handle_analysis_request(self, event: Event) -> list[Event]:
        test_summary = event.payload.get("test_summary", {})

        design_text = ""
        for md_file in self._project_dir.glob("*.md"):
            design_text = md_file.read_text()
            break

        code_files = self._read_code_files()
        report = await self._analyze(design_text, code_files, test_summary)

        if report.aligned:
            return [
                SpecAlignedEvent(
                    task_id=event.task_id,
                    from_agent=AgentName.ANALYZER,
                    to_agent=AgentName.CONTROLLER,
                    payload={"findings": ["all features present, all constraints satisfied"]},
                )
            ]

        return [
            SpecDiffFoundEvent(
                task_id=event.task_id,
                from_agent=AgentName.ANALYZER,
                to_agent=AgentName.CONTROLLER,
                payload={
                    "missing_features": report.missing_features,
                    "logic_issues": report.logic_issues,
                    "constraint_violations": report.constraint_violations,
                },
            ),
            AnalyzerFeedbackEvent(
                task_id=event.task_id,
                from_agent=AgentName.ANALYZER,
                to_agent=AgentName.BUILDER,
                payload={
                    "findings": report.missing_features + report.logic_issues + report.constraint_violations,
                    "recommendation": "Fix the identified issues",
                },
            ),
        ]

    def _read_code_files(self) -> dict[str, str]:
        files = {}
        for py_file in self._project_dir.rglob("*.py"):
            if "test_" not in py_file.name and "__pycache__" not in str(py_file):
                rel = str(py_file.relative_to(self._project_dir))
                files[rel] = py_file.read_text()
        return files

    async def _analyze(
        self, design_text: str, code_files: dict[str, str], test_summary: dict
    ) -> AnalysisReport:
        messages = self._build_analysis_prompt(design_text, code_files, test_summary)
        response_text = await self._call_llm(messages)

        try:
            data = yaml.safe_load(response_text)
            if isinstance(data, dict):
                return AnalysisReport(
                    aligned=not any(
                        data.get(k)
                        for k in ("missing_features", "logic_issues", "constraint_violations")
                    ),
                    task_type=data.get("task_type", "bugfix"),
                    missing_features=data.get("missing_features", []),
                    logic_issues=data.get("logic_issues", []),
                    constraint_violations=data.get("constraint_violations", []),
                )
        except yaml.YAMLError:
            pass

        return AnalysisReport(
            aligned=False,
            logic_issues=["Analysis failed: unable to parse analyzer response — retry needed"],
        )

    async def _call_llm(self, messages: list[dict]) -> str:
        parts = []
        for m in messages:
            role = m["role"].upper()
            parts.append(f"[{role}]\n{m['content']}")
        prompt = "\n\n".join(parts)
        text, pt, ct, tt = await opencode_completion(prompt, self._project_dir)
        log_token_usage("analyzer", "opencode/qwen3-next-80b", {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})
        return text.strip()

    def _build_analysis_prompt(
        self, design_text: str, code_files: dict[str, str], test_summary: dict
    ) -> list[dict]:
        system_prompt = self._config.system_prompt or (
            "You are an AnalyzerAgent. Compare the implementation code against the design document. "
            "First determine task_type: dev, bugfix, or optimize. "
            "Output YAML with: task_type, missing_features, logic_issues, constraint_violations. "
            "Leave empty lists if everything matches the design."
        )

        code_parts = []
        total_chars = 0
        for name, content in code_files.items():
            if total_chars < 8000:
                code_parts.append(f"--- {name} ---\n{content}")
                total_chars += len(content)

        test_text = (
            f"Test results: {test_summary.get('passed', 0)} passed, "
            f"{test_summary.get('failed', 0)} failed"
        ) if test_summary else "No test results available."

        user_prompt = (
            f"Design Document:\n{design_text[:8000]}\n\n"
            f"Current Implementation:\n" + "\n\n".join(code_parts) + "\n\n"
            f"{test_text}\n\n"
            f"Analyze gaps between the design document and the implementation. Output YAML."
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
