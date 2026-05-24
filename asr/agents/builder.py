from __future__ import annotations

import json
from pathlib import Path

from asr.agents.base import BaseAgent
from asr.agents.llm_tracker import log_token_usage
from asr.agents.opencode_backend import opencode_diff_async
from asr.config.models import AgentConfig
from asr.events.models import (
    Event, EventType, AgentName,
    CodeGeneratedEvent, PatchGeneratedEvent, ErrorOccurredEvent,
)
from asr.events.store import EventStore
from asr.spec.models import Specification


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
            if event.type == EventType.TASK_CREATED:
                return await self._handle_task_created(event)
            elif event.type == EventType.PATCH_GENERATED:
                return await self._handle_patch_request(event)
            elif event.type == EventType.TEST_FAILED:
                return await self._handle_test_failed(event)
        except Exception as e:
            return [ErrorOccurredEvent(
                task_id=event.task_id, from_agent=AgentName.BUILDER,
                to_agent=AgentName.CONTROLLER,
                payload={"agent": "builder", "error_type": type(e).__name__,
                         "error_message": str(e), "retry_hint": "retryable"},
            )]
        return []

    async def _handle_task_created(self, event: Event) -> list[Event]:
        spec_data = event.payload.get("spec", {})
        spec = Specification(**spec_data)
        return await self._generate_initial_code(event.task_id, spec)

    async def _generate_initial_code(self, task_id: str, spec: Specification) -> list[Event]:
        prompt = self._build_task_prompt()
        diff_text = await self._call_opencode(prompt)
        return [CodeGeneratedEvent(
            task_id=task_id, from_agent=AgentName.BUILDER,
            to_agent=AgentName.CONTROLLER,
            payload={"files_modified": ["main.py"], "diff_text": diff_text},
        )]

    async def _handle_test_failed(self, event: Event) -> list[Event]:
        failures = event.payload.get("failures", [])
        return await self._generate_patch(event.task_id, failures, [])

    async def _handle_patch_request(self, event: Event) -> list[Event]:
        failures = event.payload.get("failures", [])
        feedback = event.payload.get("feedback", [])
        return await self._generate_patch(event.task_id, failures, feedback)

    async def _generate_patch(self, task_id: str, failures: list[dict], feedback: list[str]) -> list[Event]:
        prompt = self._build_patch_prompt(failures, feedback)
        diff_text = await self._call_opencode(prompt)
        return [PatchGeneratedEvent(
            task_id=task_id, from_agent=AgentName.BUILDER,
            to_agent=AgentName.CONTROLLER,
            payload={"file_path": "main.py", "diff_text": diff_text,
                     "reason": f"Fix {len(failures)} test failures" if failures else "Apply improvements"},
        )]

    async def _call_opencode(self, prompt: str) -> str:
        diff, sid, pt, ct, tt = await opencode_diff_async(
            prompt, self._project_dir, self._opencode_session_id)
        log_token_usage("builder", "opencode/qwen3-next-80b",
                        {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})
        if sid:
            self._opencode_session_id = sid
        return diff if diff and diff != "no changes" else "```diff\n" + diff + "\n```"

    def _build_task_prompt(self) -> str:
        return (
            "1. 读取 DESIGN.md 了解系统设计\n"
            "2. 根据设计完成开发\n"
            "3. git add -A && git commit -m 'builder'\n"
        )

    def _build_patch_prompt(self, failures: list[dict], feedback: list[str]) -> str:
        base = (
            "读取 DESIGN.md 了解系统设计\n"
        )
        if failures:
            failure_text = "\n".join(
                f"- {f.get('nodeid', 'unknown')}: {f.get('message', 'no message')}"
                for f in failures
            )
            base += (
                f"以下测试失败，分析根因并修复代码：\n{failure_text}\n"
            )
        elif feedback:
            base += (
                f"发现以下开发的系统与 DESIGN.md 的偏差，修复：\n" +
                "\n".join(f"- {fb}" for fb in feedback) + "\n"
            )
        else:
            import random
            opts = [
                "评分 1-10，找出弱点并改进",
                "从第一性原理出发，找出合理与不合理之处，优化不合理部分",
                "对照 DESIGN.md 检查遗漏功能，补全",
                "检查代码质量：重复、不清晰、缺错误处理，重构",
            ]
            base += random.choice(opts) + "\n"
        return base
