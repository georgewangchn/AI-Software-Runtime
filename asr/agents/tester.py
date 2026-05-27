from __future__ import annotations

import re
import shutil
import subprocess
import sys
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


def _parse_pytest_output(stdout: str) -> dict:
    """Parse pytest -v --tb=short output into structured results.

    Handles lines like:
        tests/test_foo.py::test_example PASSED  [ 33%]
        tests/test_foo.py::test_baz FAILED      [ 66%]
    And the "short test summary info" section for failure messages.
    """
    lines = stdout.split("\n")

    passed = 0
    failed_nodes: list[str] = []
    error_nodes: list[str] = []
    failures_detail: dict[str, str] = {}

    for line in lines:
        stripped = line.strip()
        if "::" not in stripped:
            continue
        parts = stripped.split(" ")
        if len(parts) < 2:
            continue
        nodeid = parts[0]
        status = parts[1]

        if "::" not in nodeid:
            continue

        if status == "PASSED":
            passed += 1
        elif status == "FAILED":
            failed_nodes.append(nodeid)
        elif status == "ERROR":
            error_nodes.append(nodeid)

    in_summary = False
    for line in lines:
        if "short test summary info" in line:
            in_summary = True
            continue
        if in_summary:
            stripped = line.strip()
            if not stripped or stripped.startswith("="):
                break
            match = re.match(r'(FAILED|ERROR)\s+(\S+)\s*[-:]\s*(.*)', stripped)
            if match:
                status_type = match.group(1)
                nid = match.group(2)
                msg = match.group(3).strip()
                failures_detail[nid] = msg

    total = passed + len(failed_nodes) + len(error_nodes)

    failures = []
    for nid in failed_nodes:
        failures.append({
            "nodeid": nid,
            "message": failures_detail.get(nid, ""),
            "traceback": "",
        })
    for nid in error_nodes:
        failures.append({
            "nodeid": nid,
            "message": failures_detail.get(nid, "collection error"),
            "traceback": "",
        })

    return {
        "total": total,
        "passed": passed,
        "failed": len(failed_nodes),
        "errors": len(error_nodes),
        "failures": failures,
    }


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

        sandbox_tests = sandbox / "tests"
        has_existing_tests = sandbox_tests.exists() and any(
            f.suffix == ".py" for f in sandbox_tests.rglob("test_*.py")
        )

        if not has_existing_tests:
            prompt = (
                "1. 读取 DESIGN.md 了解系统设计\n"
                "2. 读取所有工程代码\n"
                "3. 生成 pytest 测试文件到 tests/ 目录\n"
                "4. 回复末尾输出 ### DONE"
            )
            try:
                _, pt, ct, tt = await opencode_completion(prompt, sandbox)
                log_token_usage("tester", "opencode/qwen3-next-80b", {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})
            except Exception as e:
                shutil.rmtree(sandbox, ignore_errors=True)
                return [TestErrorEvent(
                    task_id=event.task_id, from_agent=AgentName.TESTER,
                    to_agent=AgentName.CONTROLLER,
                    payload={"error_message": f"opencode timeout/failure: {str(e)}", "exit_code": -1},
                )]

        pip_req = sandbox / "requirements.txt"
        if pip_req.exists():
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(pip_req), "-q"],
                capture_output=True, text=True, timeout=300, cwd=str(sandbox),
            )

        # Run pytest with text output (no --json-report dependency)
        try:
            result = subprocess.run(
                ["pytest", "-v", "--tb=short", str(sandbox)],
                capture_output=True, text=True, timeout=120, cwd=str(sandbox),
            )
        except subprocess.TimeoutExpired:
            shutil.rmtree(sandbox, ignore_errors=True)
            return [TestErrorEvent(
                task_id=event.task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={"error_message": "pytest timed out after 120s", "exit_code": -1},
            )]
        except Exception as e:
            shutil.rmtree(sandbox, ignore_errors=True)
            return [TestErrorEvent(
                task_id=event.task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                    payload={"error_message": f"pytest invocation failed: {str(e)}", "exit_code": -1},
            )]

        parsed = _parse_pytest_output(result.stdout)
        total = parsed["total"]
        passed = parsed["passed"]
        failed = parsed["failed"]
        errors = parsed["errors"]
        failures = parsed["failures"]

        # Persist generated test files back to the project
        sandbox_tests = sandbox / "tests"
        if sandbox_tests.exists() and sandbox_tests.is_dir():
            project_tests = self._project_dir / "tests"
            if project_tests.exists():
                shutil.rmtree(project_tests, ignore_errors=True)
            shutil.copytree(sandbox_tests, project_tests)
        shutil.rmtree(sandbox, ignore_errors=True)

        if not total:
            return [TestErrorEvent(
                task_id=event.task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={"error_message": result.stderr or "No tests discovered", "exit_code": result.returncode},
            )]

        if failed > 0 or errors > 0:
            return [TestFailedEvent(
                task_id=event.task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={"total": total, "passed": passed, "failed": failed,
                         "errors": errors, "coverage": 0.0,
                         "failures": failures},
            )]
        return [TestPassedEvent(
            task_id=event.task_id, from_agent=AgentName.TESTER,
            to_agent=AgentName.CONTROLLER,
            payload={"total": total, "passed": passed, "duration": 0, "coverage": 0.0},
        )]
