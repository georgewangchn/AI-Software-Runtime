from __future__ import annotations

from pathlib import Path

from asr.agents.base import BaseAgent
from asr.agents.llm_tracker import log_token_usage
from asr.agents.opencode_backend import opencode_diff_async
from asr.config.models import AgentConfig
from asr.events.models import (
    Event, EventType, AgentName,
    PatchGeneratedEvent, ErrorOccurredEvent,
)
from asr.events.store import EventStore


def _compute_diff_summary(diff_text: str) -> dict:
    if not diff_text or diff_text == "no changes":
        return {"files": 0, "added": 0, "removed": 0, "bypass_detected": False, "risk_score": 0}

    lines = diff_text.split("\n")
    added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    files_touched = max(1, len([l for l in lines if l.startswith("--- a/")]))
    bypass_detected = any(p in diff_text for p in [
        "except:", "pass", "if DEBUG:", "return expected",
        "mock(", "@pytest.mark.skip",
    ])
    risk_score = min(100, added * 2 + removed * 3 + files_touched * 10 + (25 if bypass_detected else 0))
    return {
        "files": files_touched,
        "added": added,
        "removed": removed,
        "bypass_detected": bypass_detected,
        "risk_score": risk_score,
    }


class BuilderAgent(BaseAgent):
    def __init__(self, config: AgentConfig, event_store: EventStore, project_dir: Path):
        super().__init__(name=AgentName.BUILDER, event_store=event_store)
        self._config = config
        self._project_dir = project_dir
        self._opencode_session_id: str | None = None

    async def process(self, event: Event) -> list[Event]:
        if not self.validate_event(event):
            return []
        try:
            if event.type == EventType.PATCH_REQUESTED:
                return await self._handle_patch_request(event)
        except Exception as e:
            return [ErrorOccurredEvent(
                task_id=event.task_id, from_agent=AgentName.BUILDER,
                to_agent=AgentName.CONTROLLER,
                payload={"agent": "builder", "error_type": type(e).__name__,
                         "error_message": str(e), "retry_hint": "retryable"},
            )]
        return []

    async def _handle_patch_request(self, event: Event) -> list[Event]:
        failures = event.payload.get("failures", [])
        feedback = event.payload.get("feedback", [])
        return await self._generate_patch(event.task_id, failures, feedback)

    async def _generate_patch(self, task_id: str, failures: list[dict], feedback: list[str]) -> list[Event]:
        prompt = self._build_patch_prompt(failures, feedback)
        diff_text = await self._call_opencode(prompt)
        summary = _compute_diff_summary(diff_text)
        return [PatchGeneratedEvent(
            task_id=task_id, from_agent=AgentName.BUILDER,
            to_agent=AgentName.CONTROLLER,
            payload={
                "summary": summary,
                "reason": f"Fix {len(failures)} test failures" if failures else "Apply improvements",
            },
        )]

    async def _call_opencode(self, prompt: str) -> str:
        diff, sid, pt, ct, tt = await opencode_diff_async(
            prompt, self._project_dir, self._opencode_session_id)
        log_token_usage("builder", "opencode/qwen3-next-80b",
                        {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})
        if sid:
            self._opencode_session_id = sid
        return diff

    def _build_task_prompt(self) -> str:
        return (
            '''你是一个开发专家，根据设计文档DESIGN.md完成开发与自动化测试，交付一个可运行的完整系统：
            1. 读取 DESIGN.md，理解系统架构；
            2. 根据 DESIGN.md 进行完整的系统开发；
            3. 每开发一个功能都需要进行自动化测试；
            4. 遵循DESIGN.md/遵循第一性原理/遵循软件开发规范/遵循可交付原则;
            5. 结束输出 ### DONE'''
        )

    def _build_patch_prompt(self, failures: list[dict], feedback: list[str]) -> str:
        base = "你是一个开发专家，正在根据设计文档DESIGN.md进行开发与自动化测试。请根据以下信息改进代码：\n"
        if failures:
            failure_text = "\n".join(
                f"- {f.get('nodeid', 'unknown')}: {f.get('message', 'no message')}"
                for f in failures
            )
            base += f"修复以下测试失败：\n{failure_text}\n"
        if feedback:
            base += "修复以下偏差：\n" + "\n".join(f"- {fb}" for fb in feedback) + "\n"
        if not failures and not feedback:
            py_files = list(self._project_dir.rglob("*.py"))
            has_code = any("__pycache__" not in str(p) and "test_" not in p.name for p in py_files)
            if not has_code:
                return self._build_task_prompt()
            import random
            opts = [
                "评分 1-10 并改进代码",
                "从第一性原理优化不合理之处",
                "对照 DESIGN.md 补全遗漏功能",
                "重构提升代码质量",
            ]
            base += random.choice(opts) + "\n"
        base += "结束输出 ### DONE"
        return base
