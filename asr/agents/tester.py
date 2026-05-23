from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from asr.agents.base import BaseAgent
from asr.agents.llm_tracker import log_token_usage
from asr.agents.opencode_backend import opencode_completion
from asr.config.models import AgentConfig
from asr.events.models import (
    Event,
    EventType,
    AgentName,
    TestFailedEvent,
    TestPassedEvent,
    TestErrorEvent,
    ErrorOccurredEvent,
)
from asr.events.store import EventStore


@dataclass
class FailureInfo:
    nodeid: str
    message: str = ""
    traceback: str = ""
    lineno: int = 0


@dataclass
class TestReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    failures: list[FailureInfo] = field(default_factory=list)
    duration: float = 0.0
    coverage: float = 0.0


class TesterAgent(BaseAgent):
    def __init__(
        self,
        config: AgentConfig,
        event_store: EventStore,
        project_dir: Path,
    ):
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
            return [
                ErrorOccurredEvent(
                    task_id=event.task_id,
                    from_agent=AgentName.TESTER,
                    to_agent=AgentName.CONTROLLER,
                    payload={
                        "agent": "tester",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "retry_hint": "retryable",
                    },
                )
            ]

        return []

    async def _handle_test_started(self, event: Event) -> list[Event]:
        compile_result = self._run_compile_check()
        if not compile_result["success"]:
            return [TestErrorEvent(
                task_id=event.task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={"error_message": f"Compile error: {compile_result['errors']}", "exit_code": 1},
            )]

        design_text = ""
        for md_file in self._project_dir.glob("*.md"):
            design_text = md_file.read_text()
            break

        code_files = {}
        for py_file in self._project_dir.rglob("*.py"):
            if py_file.name.startswith("test_") or py_file.name.startswith("_asr_"):
                continue
            if "__pycache__" in str(py_file):
                continue
            code_files[py_file.name] = py_file.read_text()
        code_text = "\n\n".join(f"--- {n} ---\n{c}" for n, c in code_files.items())

        prompt = (
            f"Generate pytest tests for this project based on the design document. "
            f"Read the design and code, then write tests that verify ALL features and requirements. "
            f"Output ONLY valid Python code, no markdown.\n\n"
            f"Design Document:\n{design_text[:8000] or '(no design doc — test all functionality)'}\n\n"
            f"Code:\n{code_text[:8000]}"
        )
        test_code, pt, ct, tt = await opencode_completion(prompt, self._project_dir)
        log_token_usage("tester", "opencode/qwen3-next-80b", {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})

        test_code = re.sub(r"```(?:python)?\s*", "", test_code)
        test_code = re.sub(r"```\s*$", "", test_code)
        test_code = test_code.strip()

        if not test_code or "def test_" not in test_code:
            report = self._run_pytest([str(self._project_dir)])
        else:
            test_file = self._project_dir / "_asr_generated_test.py"
            test_file.write_text(test_code)
            try:
                report = self._run_pytest([str(test_file)])
            finally:
                test_file.unlink(missing_ok=True)

        if report.errors > 0 and report.passed == 0 and report.failed == 0:
            return [TestErrorEvent(
                task_id=event.task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={"error_message": "pytest infrastructure error", "exit_code": report.errors},
            )]

        if report.failed > 0 or report.errors > 0:
            return [TestFailedEvent(
                task_id=event.task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={
                    "total": report.total, "passed": report.passed,
                    "failed": report.failed, "errors": report.errors,
                    "coverage": report.coverage,
                    "failures": [{"nodeid": f.nodeid, "message": f.message, "traceback": f.traceback}
                                 for f in report.failures],
                },
            )]

        return [TestPassedEvent(
            task_id=event.task_id, from_agent=AgentName.TESTER,
            to_agent=AgentName.CONTROLLER,
            payload={"total": report.total, "passed": report.passed,
                     "duration": report.duration, "coverage": report.coverage},
        )]

    def _run_pytest(self, test_paths: list[str]) -> TestReport:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            report_path = f.name

        start = time.time()

        cmd = [
            "pytest",
            "--json-report",
            f"--json-report-file={report_path}",
            "--tb=short",
            "-q",
        ]
        if self._has_pytest_cov():
            cmd.extend(["--cov=.", "--cov-report=json"])
        cmd.extend(test_paths)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self._config.model.timeout or 120,
            cwd=str(self._project_dir),
        )

        duration = time.time() - start
        coverage = self._measure_coverage()

        try:
            report_data = json.loads(Path(report_path).read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return TestReport(
                total=0, errors=1,
                failures=[FailureInfo(nodeid="pytest", message=result.stderr or "unknown error")],
                duration=duration, coverage=coverage,
            )
        finally:
            Path(report_path).unlink(missing_ok=True)

        summary = report_data.get("summary", {})
        tests = report_data.get("tests", [])

        failures = []
        for test in tests:
            if test.get("outcome") == "failed":
                call_info = test.get("call", {})
                crash = call_info.get("crash", {})
                failures.append(
                    FailureInfo(
                        nodeid=test.get("nodeid", ""),
                        message=crash.get("message", call_info.get("longrepr", "")),
                        traceback=call_info.get("longrepr", ""),
                    )
                )

        return TestReport(
            total=summary.get("total", 0),
            passed=summary.get("passed", 0),
            failed=summary.get("failed", 0),
            errors=summary.get("error", 0),
            failures=failures,
            duration=duration,
            coverage=coverage,
        )

    def _measure_coverage(self) -> float:
        try:
            report_result = subprocess.run(
                ["coverage", "report", "--format=total"],
                capture_output=True, text=True, timeout=10,
                cwd=str(self._project_dir),
            )
            try:
                return float(report_result.stdout.strip()) / 100.0
            except ValueError:
                return 0.0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return 0.0

    def _has_pytest_cov(self) -> bool:
        try:
            import pytest_cov
            return True
        except ImportError:
            return False

    def _run_compile_check(self) -> dict:
        import sys
        py_files = [f for f in self._project_dir.rglob("*.py")
                    if "test_" not in f.name and "__pycache__" not in str(f)]
        if not py_files:
            return {"success": True, "errors": []}

        try:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile"] + [str(f) for f in py_files],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return {"success": False, "errors": [result.stderr[:500]]}
            return {"success": True, "errors": []}
        except subprocess.TimeoutExpired:
            return {"success": False, "errors": ["compile check timed out"]}
        except Exception as e:
            return {"success": False, "errors": [str(e)]}
