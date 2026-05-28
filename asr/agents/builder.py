from __future__ import annotations

from pathlib import Path

from asr.agents.base import BaseAgent
from asr.agents.llm_tracker import log_token_usage
from asr.agents.opencode_backend import opencode_run
from asr.config.models import AgentConfig
from asr.events.models import (
    Event, EventType, AgentName,
    PatchGeneratedEvent, ErrorOccurredEvent,
)
from asr.events.store import EventStore


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
        sid, pt, ct, tt = await opencode_run(prompt, self._project_dir, self._opencode_session_id)
        log_token_usage("builder", "opencode/qwen3-next-80b",
                        {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})
        if sid:
            self._opencode_session_id = sid
        return [PatchGeneratedEvent(
            task_id=task_id, from_agent=AgentName.BUILDER,
            to_agent=AgentName.CONTROLLER,
            payload={
                "reason": f"Fix {len(failures)} test failures" if failures else "Apply improvements",
            },
        )]

    def _build_task_prompt(self) -> str:
        return (
            '''根据设计文档 DESIGN.md 完成系统开发。
            1. 读取 DESIGN.md，理解全部功能需求和系统架构；
            2. 逐模块完成开发，每个模块必须包含完整的功能代码和业务逻辑；
            3. 不要创建空的 __init__.py 或骨架目录；
            4. 为每个模块编写基本的单元测试；
            5. 开发完成前自检：对比 DESIGN.md，确认所有功能点都已实现
            6. 如果有遗漏的功能模块，继续开发直到全部完成'''
        )

    def _build_patch_prompt(self, failures: list[dict], feedback: list[str]) -> str:
        base = "你是一个开发专家，和你配合的有测试专家、验收专家。开发流程是：开发专家开发代码 -> 测试专家编写测试用例 -> 验收专家验收结果 -> 反馈给开发专家。\n"
        base += "你收到了测试专家和验收专家的反馈，请根据以下信息改进代码：\n"
        if failures:
            failure_text = "\n".join(
                f"- {f.get('nodeid', 'unknown')}: {f.get('message', 'no message')}"
                for f in failures
            )
            base += f"\n测试专家发现的测试失败：\n{failure_text}\n"
        if feedback:
            base += "\n验收专家发现的问题：\n\n"
            for fb in feedback:
                if fb.startswith("[PRIORITY]") or fb.startswith("[COMPILE_ERROR]") or fb.startswith("[ANALYZER_ERROR]"):
                    base += f"**{fb}**\n\n"
                else:
                    base += fb + "\n"
            base += "\n"
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
                "分析一遍最近几轮的改动，推演一遍设计意图，看看是否有不合理的地方并改进",
            ]
            base += random.choice(opts) + "\n"
        return base
