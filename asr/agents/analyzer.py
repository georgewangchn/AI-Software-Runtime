from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

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
    full_text: str = ""
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
        test_summary = event.payload.get("test_summary", {})
        report = await self._analyze(test_summary)
        if report.aligned:
            return [SpecAlignedEvent(
                task_id=event.task_id, from_agent=AgentName.ANALYZER,
                to_agent=AgentName.CONTROLLER,
                payload={"findings": ["all features present, all constraints satisfied"]},
            )]
        findings = [report.full_text] if report.full_text else []
        return [
            SpecDiffFoundEvent(
                task_id=event.task_id, from_agent=AgentName.ANALYZER,
                to_agent=AgentName.CONTROLLER,
                payload={"missing_features": findings,
                         "logic_issues": [],
                         "constraint_violations": []},
            ),
            AnalyzerFeedbackEvent(
                task_id=event.task_id, from_agent=AgentName.ANALYZER,
                to_agent=AgentName.BUILDER,
                payload={"findings": findings, "recommendation": "",
                         "high_severity_count": report.high_severity_count},
            ),
        ]

    async def _analyze(self, test_summary: dict | None = None) -> AnalysisReport:
        test_info = ""
        if test_summary:
            total = test_summary.get("total", 0)
            passed = test_summary.get("passed", 0)
            failed = test_summary.get("failed", 0)
            failures = test_summary.get("failures", [])
            if total > 0:
                test_info = f"\n测试结果：共{total}个测试，通过{passed}个，失败{failed}个。\n"
                if failures:
                    test_info += "失败测试：\n" + "\n".join(
                        f"  - {f.get('nodeid', '?')}: {f.get('message', '?')}"
                        for f in failures[:5]
                    ) + "\n"
            elif total == 0 and passed == 0:
                test_info = "\n注意：当前没有任何测试通过，项目可能无法编译或缺少测试文件。\n"

        prompt = (
            test_info +
            "1. 读取 DESIGN.md 了解系统设计\n"
            "2. 分析系统代码\n"
            "3. 对比设计文档与实现代码，重点关注测试失败对应的功能模块\n"
            "4. 按以下分类输出分析结果，使用清晰的小标题和项目符号：\n"
            "   - 缺失功能：DESIGN.md 要求但未实现的功能\n"
            "   - 逻辑错误：实现方式与设计文档不符\n"
            "   - 违反约束：不符合 DESIGN.md 规定的约束条件\n"
            "   - 推演偏差：从第一性原理推演设计意图与实现不符\n"
            "5. 每个问题标注严重程度 [HIGH]/[MEDIUM]/[LOW]\n"
            "6. 如果实现完全符合设计文档，只输出 ALL CLEAR\n"
            "7. 直接输出分析文本，不要写文件"
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
            text, pt, ct, tt = await opencode_completion(prompt, sandbox)
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)

        log_token_usage("analyzer", "opencode/qwen3-next-80b", {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})

        if not text or not text.strip():
            return AnalysisReport(aligned=False, full_text="Analyzer produced no output")

        if re.search(r'ALL\s*CLEAR', text, re.IGNORECASE):
            return AnalysisReport(aligned=True)

        high_count = len(re.findall(r'\[HIGH\]|\[CRITICAL\]', text, re.IGNORECASE))

        return AnalysisReport(
            aligned=False,
            full_text=text.strip(),
            high_severity_count=high_count,
        )
