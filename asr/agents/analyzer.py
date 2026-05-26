from __future__ import annotations

import re
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
    high_severity_count: int = 0


class AnalyzerAgent(BaseAgent):
    def __init__(self, config: AgentConfig, event_store: EventStore, project_dir: Path):
        super().__init__(name=AgentName.ANALYZER, event_store=event_store)
        self._config = config
        self._project_dir = project_dir

    async def process(self, event: Event) -> list[Event]:
        if not self.validate_event(event):
            return []
        try:
            if event.type == EventType.ANALYZE_REQUESTED:
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
                payload={"findings": findings, "recommendation": "Fix the identified issues",
                         "high_severity_count": report.high_severity_count},
            ),
        ]

    async def _analyze(self) -> AnalysisReport:
        prompt = (
            "1. 读取 DESIGN.md 和所有 .py 代码文件\n"
            "2. 对比设计文档与实现代码\n"
            "3. 将分析结果写入 analysis.yaml 文件：\n"
            "   task_type: dev\n"
            "   missing_features: []\n"
            "   logic_issues: []\n"
            "   constraint_violations: []\n"
            "4. 仅分析：缺失功能、逻辑错误、违反约束\n"
            "5. 无问题时所有列表为空数组 []"
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

        pt = ct = tt = 0
        try:
            _, pt, ct, tt = await opencode_completion(prompt, sandbox)
            yaml_file = sandbox / "analysis.yaml"
            if yaml_file.exists():
                text = yaml_file.read_text()
            else:
                text = ""
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)

        log_token_usage("analyzer", "opencode/qwen3-next-80b", {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})

        try:
            cleaned = text
            m = re.search(r"```(?:yaml)?\s*\n(.*?)```", cleaned, re.DOTALL)
            if m:
                cleaned = m.group(1)
            else:
                for marker in ("task_type:", "missing_features:", "logic_issues:", "constraint_violations:"):
                    idx = cleaned.find(marker)
                    if idx > 0:
                        cleaned = cleaned[idx:]
                        break
            data = yaml.safe_load(cleaned)

            if not isinstance(data, dict):
                raise ValueError("Response is not a YAML dictionary")

            missing_features = self._extract_descriptions(data.get("missing_features", []))
            logic_issues = self._extract_descriptions(data.get("logic_issues", []))
            constraint_violations = self._extract_descriptions(data.get("constraint_violations", []))

            high_count = 0
            for items in [data.get("missing_features", []), data.get("logic_issues", []), data.get("constraint_violations", [])]:
                for item in (items if isinstance(items, list) else []):
                    if isinstance(item, dict) and item.get("severity") in ("critical", "high"):
                        high_count += 1

            return AnalysisReport(
                aligned=not (missing_features or logic_issues or constraint_violations),
                task_type=data.get("task_type", "bugfix"),
                missing_features=missing_features,
                logic_issues=logic_issues,
                constraint_violations=constraint_violations,
                high_severity_count=high_count,
            )
        except (yaml.YAMLError, ValueError, TypeError) as e:
            return AnalysisReport(
                aligned=False,
                task_type="bugfix",
                missing_features=[],
                logic_issues=[f"Analysis failed: unable to parse response - {str(e)}"],
                constraint_violations=[],
            )

    def _extract_descriptions(self, items: list) -> list[str]:
        result = []
        for item in (items if isinstance(items, list) else []):
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                desc = item.get("description", str(item))
                sev = item.get("severity", "")
                result.append(f"[{sev}] {desc}" if sev else desc)
        return result
