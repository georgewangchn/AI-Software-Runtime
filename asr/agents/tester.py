from __future__ import annotations

import re
import shutil
from pathlib import Path

from asr.agents.base import BaseAgent
from asr.agents.llm_tracker import log_token_usage
from asr.agents.opencode_backend import opencode_completion
from asr.config.models import AgentConfig
from asr.events.models import (
    Event, EventType, AgentName,
    TestFailedEvent, TestPassedEvent, TestErrorEvent, ErrorOccurredEvent,
)
from asr.events.store import EventStore


class TesterAgent(BaseAgent):
    def __init__(self, config: AgentConfig, event_store: EventStore, project_dir: Path):
        super().__init__(name=AgentName.TESTER, event_store=event_store)
        self._config = config
        self._project_dir = project_dir

    async def process(self, event: Event) -> list[Event]:
        if not self.validate_event(event):
            return []
        try:
            if event.type == EventType.TEST_STARTED:
                return await self._handle_test_started(event)
        except Exception as e:
            return [ErrorOccurredEvent(
                task_id=event.task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={"agent": "tester", "error_type": type(e).__name__,
                         "error_message": str(e), "retry_hint": "retryable"},
            )]
        return []

    async def _handle_test_started(self, event: Event) -> list[Event]:
        sandbox = self._project_dir / ".asr_sandbox" / "tester"
        if sandbox.exists():
            shutil.rmtree(sandbox, ignore_errors=True)
        sandbox.mkdir(parents=True, exist_ok=True)

        has_code = False
        for f in self._project_dir.rglob("*"):
            if f.is_dir():
                continue
            if any(p in str(f) for p in ("__pycache__", ".asr_sandbox", ".git/", ".runtime", ".pytest_cache")):
                continue
            rel = f.relative_to(self._project_dir)
            dst = sandbox / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
            if f.suffix == ".py":
                has_code = True

        if not has_code:
            shutil.rmtree(sandbox, ignore_errors=True)
            return [TestFailedEvent(
                task_id=event.task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={"total": 1, "passed": 0, "failed": 1, "errors": 0,
                         "failures": [{"nodeid": "no_code", "message": "No Python files to test"}]},
            )]

        prompt = (
            "1. 读取 DESIGN.md 了解系统设计\n"
            "2. 读取工程代码\n"
            "3. 生成 pytest 测试，写入 test_verify.py\n"
            "4. 执行 pytest test_verify.py -q --tb=short\n"
            "5. 在回复末尾输出一行 YAML 格式的测试结果：\n"
            "   ```yaml\n"
            "   passed: <number>\n"
            "   failed: <number>\n"
            "   failures:\n"
            "     - nodeid: <test name>\n"
            "       message: <failure message>\n"
            "   ```"
        )
        output, pt, ct, tt = await opencode_completion(prompt, sandbox)
        log_token_usage("tester", "opencode/qwen3-next-80b", {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})
        shutil.rmtree(sandbox, ignore_errors=True)

        return self._parse_test_output(event.task_id, output)

    def _parse_test_output(self, task_id: str, output: str) -> list[Event]:
        import yaml
        try:
            m = re.search(r"```yaml\s*\n(.*?)```", output, re.DOTALL)
            yaml_text = m.group(1) if m else output
            data = yaml.safe_load(yaml_text)
            if isinstance(data, dict):
                passed = data.get("passed", 0)
                failed = data.get("failed", 0)
                failures = data.get("failures", [])
                total = passed + failed

                if failed > 0:
                    return [TestFailedEvent(
                        task_id=task_id, from_agent=AgentName.TESTER,
                        to_agent=AgentName.CONTROLLER,
                        payload={"total": total, "passed": passed, "failed": failed,
                                 "errors": 0, "coverage": 0.0,
                                 "failures": [{"nodeid": f.get("nodeid", "?"),
                                               "message": f.get("message", ""),
                                               "traceback": ""} for f in failures]},
                    )]
                return [TestPassedEvent(
                    task_id=task_id, from_agent=AgentName.TESTER,
                    to_agent=AgentName.CONTROLLER,
                    payload={"total": total, "passed": passed, "duration": 0, "coverage": 0.0},
                )]
        except Exception:
            return [TestErrorEvent(
                task_id=task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={"error_message": f"Failed to parse test output: {output[:200]}", "exit_code": 1},
            )]
