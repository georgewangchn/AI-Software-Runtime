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

# Patterns to skip when syncing sandbox
_SKIP_PATTERNS = ("__pycache__", ".asr_sandbox", ".git/", ".runtime", ".pytest_cache")

# Name of the report file that opencode writes its final analysis into
_ANALYSIS_REPORT_FILE = "ANALYSIS_REPORT.md"


@dataclass
class AnalysisReport:
    aligned: bool = False
    full_text: str = ""
    high_severity_count: int = 0
    findings: list[str] = field(default_factory=list)


def _split_findings(text: str) -> list[str]:
    """Split the raw analysis text into independent finding items.

    Each finding is a self-contained observation with its severity level.
    """
    if not text or not text.strip():
        return []

    # Strategy 1: Split by category+severity markers (new format)
    cat_severity_pattern = re.compile(
        r'(?=\[(?:MISSING|LOGIC|CONSTRAINT|DEVIATION)\]\s*\[(?:HIGH|MEDIUM|LOW|CRITICAL)\])',
        re.IGNORECASE,
    )
    parts = cat_severity_pattern.split(text.strip())
    if len(parts) > 1:
        return [p.strip() for p in parts if p.strip()]

    # Strategy 2: Split by severity markers only (old format)
    sev_pattern = re.compile(r'(?=\[(?:HIGH|MEDIUM|LOW|CRITICAL)\])', re.IGNORECASE)
    parts = sev_pattern.split(text.strip())
    if len(parts) > 1:
        findings = [
            p.strip() for p in parts
            if p.strip() and re.search(r'\[(?:HIGH|MEDIUM|LOW|CRITICAL)\]', p, re.IGNORECASE)
        ]
        if len(findings) > 1:
            return findings

    # Strategy 3: Split by numbered items or bullet points
    lines = text.strip().split("\n")
    numbered_pattern = re.compile(r'^\s*[\d]+[\.\)、]\s')
    bullet_pattern = re.compile(r'^\s*[-*•]\s')

    if any(numbered_pattern.match(l) for l in lines) or any(bullet_pattern.match(l) for l in lines):
        findings: list[str] = []
        current: list[str] = []
        for line in lines:
            if numbered_pattern.match(line) or bullet_pattern.match(line):
                if current:
                    findings.append("\n".join(current).strip())
                current = [line]
            else:
                current.append(line)
        if current:
            findings.append("\n".join(current).strip())
        return [f for f in findings if f]

    # Strategy 4: Split by category section headers
    section_pattern = re.compile(r'^(?:[#]+\s*)?(?:缺失功能|逻辑错误|违反约束|推演偏差|问题|分析)', re.IGNORECASE)
    sections: list[str] = []
    current: list[str] = []
    for line in lines:
        if section_pattern.match(line.strip()):
            if current:
                sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current).strip())
    if len(sections) > 1:
        return [s for s in sections if s]

    # Strategy 5: Split by double newline (paragraph boundaries)
    if "\n\n" in text:
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(paras) > 1:
            return paras

    # Fallback: return as single item
    return [text.strip()]


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

        findings = report.findings if report.findings else [report.full_text] if report.full_text else []
        missing_features, logic_issues, constraint_violations = _classify_findings(findings)

        return [
            SpecDiffFoundEvent(
                task_id=event.task_id, from_agent=AgentName.ANALYZER,
                to_agent=AgentName.CONTROLLER,
                payload={"missing_features": missing_features,
                         "logic_issues": logic_issues,
                         "constraint_violations": constraint_violations},
            ),
            AnalyzerFeedbackEvent(
                task_id=event.task_id, from_agent=AgentName.ANALYZER,
                to_agent=AgentName.BUILDER,
                payload={"findings": findings, "recommendation": "",
                         "high_severity_count": report.high_severity_count},
            ),
        ]

    async def _analyze(self, test_summary: dict | None = None) -> AnalysisReport:
        # ── Build test info ──
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

        # ── Build the prompt — opencode can use tools, but must write final result to a file ──
        prompt = (
            test_info +
            "分析任务：\n"
            "1. 读取 DESIGN.md 了解系统设计\n"
            "2. 阅读所有源码文件，对比设计文档与实现代码\n"
            "3. 重点关注测试失败对应的功能模块\n\n"
            "**重要：完成所有分析后，按以下格式将最终结论写入 ANALYSIS_REPORT.md 文件。**\n\n"
            "ANALYSIS_REPORT.md 格式要求：\n"
            "- 每个发现单独一行，格式为 [CATEGORY] [SEVERITY] 具体问题描述\n"
            "- CATEGORY: MISSING（缺失功能）、LOGIC（逻辑错误）、CONSTRAINT（违反约束）、DEVIATION（推演偏差）\n"
            "- SEVERITY: [HIGH]、[MEDIUM]、[LOW]\n"
            "- 如果实现完全符合设计文档，只写 ALL CLEAR\n\n"
            "示例：\n"
            "  [MISSING] [HIGH] 用户认证模块完全未实现，DESIGN.md 第3节要求 OAuth2.0 登录\n"
            "  [LOGIC] [MEDIUM] 订单状态机 transition 与设计文档不符，缺少 'cancelled' 状态\n"
            "  [CONSTRAINT] [LOW] API 响应格式未遵循 DESIGN.md 规定的 JSON:API 规范\n\n"
            "**不要**在你的对话文本中输出分析结论。**只**写入 ANALYSIS_REPORT.md。"
            "注意:整个开发过程请自动化执行，不要再中断询问我，若有多个方案选择，自主评估决定。"
        )

        # ── Set up sandbox so opencode can explore the codebase with tools ──
        sandbox = self._project_dir / ".asr_sandbox" / "analyzer"
        if sandbox.exists():
            shutil.rmtree(sandbox, ignore_errors=True)
        sandbox.mkdir(parents=True, exist_ok=True)

        for f in self._project_dir.rglob("*"):
            if f.is_dir():
                continue
            if any(p in str(f) for p in _SKIP_PATTERNS):
                continue
            rel = f.relative_to(self._project_dir)
            dst = sandbox / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)

        # ── Call opencode — it uses tools to analyze, then writes ANALYSIS_REPORT.md ──
        pt = ct = tt = 0
        try:
            _chat_text, pt, ct, tt = await opencode_completion(prompt, sandbox, label="Analyzer")
        finally:
            # ── Read the final report file that opencode wrote, then delete it ──
            report_path = sandbox / _ANALYSIS_REPORT_FILE
            if report_path.exists():
                try:
                    report_text = report_path.read_text().strip()
                except Exception:
                    report_text = ""
                report_path.unlink(missing_ok=True)  # prevent data pollution
            else:
                report_text = ""

            shutil.rmtree(sandbox, ignore_errors=True)

        log_token_usage("analyzer", "opencode/glm-4.7-fp8",
                        {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})

        # ── Process the report ──
        if not report_text:
            return AnalysisReport(
                aligned=False,
                full_text="opencode did not write ANALYSIS_REPORT.md — analysis incomplete",
            )

        # ALL CLEAR only counts if NO [HIGH], [CRITICAL], [MEDIUM], [LOW], [MISSING], [LOGIC],
        # [CONSTRAINT], or [DEVIATION] tags are present — otherwise it's a false positive
        has_issues = bool(re.search(
            r'\[(?:HIGH|CRITICAL|MEDIUM|LOW|MISSING|LOGIC|CONSTRAINT|DEVIATION)\]',
            report_text, re.IGNORECASE
        ))
        if re.search(r'ALL\s*CLEAR', report_text, re.IGNORECASE) and not has_issues:
            return AnalysisReport(aligned=True)

        high_count = len(re.findall(r'\[HIGH\]|\[CRITICAL\]', report_text, re.IGNORECASE))
        findings = _split_findings(report_text)

        return AnalysisReport(
            aligned=False,
            full_text=report_text,
            high_severity_count=high_count,
            findings=findings,
        )


def _classify_findings(findings: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Classify each finding into missing_features / logic_issues / constraint_violations."""
    missing: list[str] = []
    logic: list[str] = []
    constraint: list[str] = []

    for f in findings:
        upper = f.upper()
        if "MISSING" in upper or "缺失" in f or "未实现" in f or "缺少" in f:
            missing.append(f)
        elif "LOGIC" in upper or "逻辑" in f or "推演" in f or "DEVIATION" in upper:
            logic.append(f)
        elif "CONSTRAINT" in upper or "约束" in f or "违反" in f:
            constraint.append(f)
        else:
            missing.append(f)

    return missing, logic, constraint
