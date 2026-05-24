from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from asr.agents.base import BaseAgent
from asr.agents.llm_tracker import log_token_usage
from asr.agents.opencode_backend import opencode_completion
from asr.config.models import AgentConfig
from asr.events.models import (
    Event, EventType, AgentName,
    SpecDiffFoundEvent, SpecAlignedEvent, AnalyzerFeedbackEvent, ErrorOccurredEvent,
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
    def __init__(self, config: AgentConfig, event_store: EventStore, project_dir: Path):
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
            return [ErrorOccurredEvent(
                task_id=event.task_id, from_agent=AgentName.ANALYZER,
                to_agent=AgentName.CONTROLLER,
                payload={"agent": "analyzer", "error_type": type(e).__name__,
                         "error_message": str(e), "retry_hint": "retryable"},
            )]
        return []

    async def _handle_analysis_request(self, event: Event) -> list[Event]:
        report = await self._analyze()
        if report.aligned:
            return [SpecAlignedEvent(
                task_id=event.task_id, from_agent=AgentName.ANALYZER,
                to_agent=AgentName.CONTROLLER,
                payload={"findings": ["all features present, all constraints satisfied"]},
            )]
        findings = report.missing_features + report.logic_issues + report.constraint_violations
        return [
            SpecDiffFoundEvent(
                task_id=event.task_id, from_agent=AgentName.ANALYZER,
                to_agent=AgentName.CONTROLLER,
                payload={"missing_features": report.missing_features,
                         "logic_issues": report.logic_issues,
                         "constraint_violations": report.constraint_violations},
            ),
            AnalyzerFeedbackEvent(
                task_id=event.task_id, from_agent=AgentName.ANALYZER,
                to_agent=AgentName.BUILDER,
                payload={"findings": findings, "recommendation": "Fix the identified issues"},
            ),
        ]

    async def _analyze(self) -> AnalysisReport:
        prompt = (
            "1. 读取 DESIGN.md 了解系统设计\n"
            "2. 读取所有工程代码\n"
            "3. 对比设计文档与实现代码，分析两者偏差（包括未实现的功能、逻辑问题、违反约束等情况）\n"
            "4. 输出 YAML（不要 markdown 代码块）：\n"
            "   task_type: dev\n"
            "   missing_features: []\n"
            "   logic_issues: []\n"
            "   constraint_violations: []\n"
            "5. 无问题时所有列表为空"
        )

        sandbox = self._project_dir / ".asr_sandbox" / "analyzer"
        if sandbox.exists():
            shutil.rmtree(sandbox, ignore_errors=True)
        sandbox.mkdir(parents=True, exist_ok=True)

        for f in self._project_dir.rglob("*"):
            if f.is_dir():
                continue
            if any(p in str(f) for p in ("__pycache__", ".asr_sandbox", ".git/", ".runtime", ".pytest_cache")):
                continue
            rel = f.relative_to(self._project_dir)
            dst = sandbox / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)

        try:
            text, pt, ct, tt = await opencode_completion(prompt, sandbox)
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)

        log_token_usage("analyzer", "opencode/qwen3-next-80b", {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})

        try:
            # Parse YAML output
            data = yaml.safe_load(text)
            
            # Validate structure
            if not isinstance(data, dict):
                raise ValueError("Response is not a YAML dictionary")
            
            # Validate required fields and types
            task_type = data.get("task_type", "bugfix")
            if not isinstance(task_type, str):
                raise ValueError("task_type must be a string")
                
            missing_features = data.get("missing_features", [])
            if not isinstance(missing_features, list):
                raise ValueError("missing_features must be a list")
                
            logic_issues = data.get("logic_issues", [])
            if not isinstance(logic_issues, list):
                raise ValueError("logic_issues must be a list")
                
            constraint_violations = data.get("constraint_violations", [])
            if not isinstance(constraint_violations, list):
                raise ValueError("constraint_violations must be a list")
            
            return AnalysisReport(
                aligned=not any(data.get(k) for k in ("missing_features", "logic_issues", "constraint_violations")),
                task_type=task_type,
                missing_features=missing_features,
                logic_issues=logic_issues,
                constraint_violations=constraint_violations,
            )
        except (yaml.YAMLError, ValueError, TypeError) as e:
            # Log the raw response for debugging (in production, this would be a structured log)
            # Return structured error response that matches the expected format
            return AnalysisReport(
                aligned=False, 
                task_type="bugfix",
                missing_features=[], 
                logic_issues=[f"Analysis failed: unable to parse response - {str(e)}"], 
                constraint_violations=[]
            )
