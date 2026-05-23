from __future__ import annotations

import json
from pathlib import Path

from asr.agents.base import BaseAgent
from asr.agents.llm_tracker import log_token_usage
from asr.agents.opencode_backend import opencode_diff_async
from asr.config.models import AgentConfig
from asr.events.models import (
    Event,
    EventType,
    AgentName,
    CodeGeneratedEvent,
    PatchGeneratedEvent,
    ErrorOccurredEvent,
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
        prompt = self._build_initial_prompt(spec)
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
        code_files = self._read_project_files()
        prompt = self._build_patch_prompt(failures, feedback, code_files)
        diff_text = await self._call_opencode(prompt)
        return [PatchGeneratedEvent(
            task_id=task_id, from_agent=AgentName.BUILDER,
            to_agent=AgentName.CONTROLLER,
            payload={"file_path": "main.py", "diff_text": diff_text,
                     "reason": f"Fix {len(failures)} test failures"},
        )]

    async def _call_opencode(self, prompt: str) -> str:
        diff, sid, pt, ct, tt = await opencode_diff_async(
            prompt, self._project_dir, self._opencode_session_id)
        log_token_usage("builder", "opencode/qwen3-next-80b",
                        {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})
        if sid:
            self._opencode_session_id = sid
        if diff and diff != "no changes":
            return diff
        return "```diff\n" + diff + "\n```"

    def _build_initial_prompt(self, spec: Specification) -> str:
        system = self._config.system_prompt or (
            "You are a BuilderAgent. Generate code from design documents. "
            "Output valid Python code. Do NOT write test files."
        )
        design_text = ""
        for md_file in self._project_dir.glob("*.md"):
            design_text = md_file.read_text()[:8000]
            break
        user = (
            f"Generate a Python project matching this design document:\n\n"
            f"{design_text}\n\n"
            f"Output the complete Python code implementing the core system."
        )
        return f"[SYSTEM]\n{system}\n\n[USER]\n{user}"

    def _build_patch_prompt(self, failures: list[dict], feedback: list[str],
                            code_files: dict[str, str]) -> str:
        system = self._config.system_prompt or (
            "You are a BuilderAgent. Generate unified diffs to fix test failures. "
            "Only modify files that need changes. Do NOT modify test files."
        )
        failure_text = "\n".join(
            f"- {f.get('nodeid', 'unknown')}: {f.get('message', 'no message')}"
            for f in failures
        )
        feedback_text = "\n".join(f"- {fb}" for fb in feedback) if feedback else "none"
        code_text = "\n\n".join(
            f"--- {name} ---\n{content}" for name, content in code_files.items()
        ) if code_files else "(no project files found)"

        user = (
            f"Current code in project:\n{code_text}\n\n"
            f"The following tests are failing:\n{failure_text}\n\n"
            f"Analyzer feedback:\n{feedback_text}\n\n"
            f"Target file to patch: main.py\n"
            f"Generate a unified diff that fixes these failures."
        )
        return f"[SYSTEM]\n{system}\n\n[USER]\n{user}"

    def _read_project_files(self) -> dict[str, str]:
        files = {}
        for py_file in self._project_dir.rglob("*.py"):
            if "test_" not in py_file.name and "__pycache__" not in str(py_file):
                rel = str(py_file.relative_to(self._project_dir))
                files[rel] = py_file.read_text()
        return files
