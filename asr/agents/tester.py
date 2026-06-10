from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import filecmp

from asr.agents.base import BaseAgent
from asr.agents.llm_tracker import log_token_usage
from asr.agents.opencode_backend import opencode_completion
from asr.config.models import AgentConfig
from asr.events.models import (
    Event, EventType, AgentName,
    TestFailedEvent, TestPassedEvent, TestErrorEvent, ErrorOccurredEvent,
)
from asr.events.store import EventStore

# Directories / patterns to always skip when syncing project <-> sandbox
_SKIP_PATTERNS = (
    "__pycache__", ".asr_sandbox", ".git/", ".runtime", ".pytest_cache",
    ".opencode", ".opencode/", "node_modules", ".venv", ".env",
)


def _sync_project_to_sandbox(project_dir: Path, sandbox: Path) -> None:
    """Incrementally sync changed files from project_dir into sandbox.

    - Creates sandbox if it doesn't exist.
    - Only copies files that are new or differ from the sandbox copy.
    - Removes sandbox files that no longer exist in the project.
    """
    sandbox.mkdir(parents=True, exist_ok=True)

    # Build set of project-relative paths for cleanup
    project_files: set[str] = set()
    for f in project_dir.rglob("*"):
        if f.is_dir():
            continue
        if any(p in str(f) for p in _SKIP_PATTERNS):
            continue
        rel = str(f.relative_to(project_dir))
        project_files.add(rel)
        dst = sandbox / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and filecmp.cmp(f, dst, shallow=False):
            continue  # identical, skip
        shutil.copy2(f, dst)

    # Remove sandbox files that no longer exist in project
    for f in sandbox.rglob("*"):
        if f.is_dir():
            continue
        if any(p in str(f) for p in _SKIP_PATTERNS):
            continue
        rel = str(f.relative_to(sandbox))
        if rel not in project_files:
            f.unlink(missing_ok=True)


def _sync_sandbox_to_project(sandbox: Path, project_dir: Path) -> list[str]:
    """Sync modified / new files from sandbox back to project_dir.

    Returns list of relative paths that were synced.
    """
    synced: list[str] = []
    for f in sandbox.rglob("*"):
        if f.is_dir():
            continue
        if any(p in str(f) for p in _SKIP_PATTERNS):
            continue
        rel = str(f.relative_to(sandbox))
        dst = project_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and filecmp.cmp(f, dst, shallow=False):
            continue  # identical, skip
        shutil.copy2(f, dst)
        synced.append(rel)
    if not synced:
        print(f"[tester] WARNING: _sync_sandbox_to_project synced 0 files. "
              f"sandbox={sandbox} project={project_dir}", file=sys.stderr)
    else:
        print(f"[tester] sync sandbox→project: {len(synced)} files", file=sys.stderr)
    return synced


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

        # Incremental sync: only copy changed/new files, don't rebuild sandbox
        _sync_project_to_sandbox(self._project_dir, sandbox)

        has_code = any(
            f.suffix == ".py"
            for f in sandbox.rglob("*")
            if f.is_file() and "__pycache__" not in str(f)
        )
        if not has_code:
            return [TestFailedEvent(
                task_id=event.task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={"total": 1, "passed": 0, "failed": 1, "errors": 0,
                         "failures": [{"nodeid": "no_code", "message": "No Python files to test"}]},
            )]


        prompt = (
            '''编写专业的测试用例：
            1. 读取 DESIGN.md 了解系统设计
            2. 读取所有工程代码
            3. 检查 tests/ 目录下已有的测试用例，如果有问题就修复
            4. 对新功能或未覆盖的代码，补充新的 test_*.py 测试文件到 tests/ 目录
            5. 确保每个 test_*.py 文件包含完整的 import 和测试函数

            **重要：完成所有测试用例编写后，创建 TESTER_COMPLETE.md 文件，总结测试结果：那些测试通过了，那些测试失败了。**
            该文件只需包含一行完成确认，例如：
            Tester completed: 5 new test files (120 tests), 2 fixed, 3 skipped
            fail: <failure_messages>
                其中 <failure_messages> 是测试过程中发现的失败或问题的简要列表，例如：
            - tests/test_payment.py::test_process_payment: 订单状态未正确更新
            - tests/test_api.py::test_get_user: API 响应缺少字段
            **不要**在对话文本中说"完成了"，要写测试结果。
            注意:整个开发过程请自动化执行，不要再中断询问我，若有多个方案选择，自主评估决定。'''
        )
        try:
            text, pt, ct, tt = await opencode_completion(prompt, sandbox, label="Tester")
            log_token_usage("tester", "opencode/glm-4.7-fp8", {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})
        except Exception as e:
            _sync_sandbox_to_project(sandbox, self._project_dir)
            return [TestErrorEvent(
                task_id=event.task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={"error_message": f"opencode timeout/failure: {str(e)}", "exit_code": -1},
            )]

        # ── Check completion marker: opencode must explicitly signal it finished ──
        complete_marker = sandbox / "TESTER_COMPLETE.md"
        if not complete_marker.exists():
            _sync_sandbox_to_project(sandbox, self._project_dir)
            return [TestErrorEvent(
                task_id=event.task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={"error_message": "opencode did not write TESTER_COMPLETE.md — test generation incomplete", "exit_code": -1},
            )]
        # Read and delete the marker to prevent data pollution in later iterations
        try:
            tester_summary = complete_marker.read_text().strip()[:200]
        except Exception:
            tester_summary = "(unreadable)"
        complete_marker.unlink(missing_ok=True)

        sandbox_tests = sandbox / "tests"
        test_files = list(sandbox_tests.rglob("test_*.py")) if sandbox_tests.exists() else []
        if not test_files:
            _sync_sandbox_to_project(sandbox, self._project_dir)
            return [TestErrorEvent(
                task_id=event.task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={"error_message": f"opencode 未生成 test_*.py 文件。完成标记: {tester_summary}", "exit_code": -1},
            )]

        pip_req = sandbox / "requirements.txt"
        if pip_req.exists():
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(pip_req), "-q", "--no-input"],
                    capture_output=True, text=True, timeout=3600, cwd=str(sandbox),
                )
            except (subprocess.TimeoutExpired, Exception):
                pass

        # Run pytest with text output (no --json-report dependency)
        try:
            result = subprocess.run(
                ["pytest", "-v", "--tb=short", str(sandbox)],
                capture_output=True, text=True, timeout=600, cwd=str(sandbox),
            )
        except subprocess.TimeoutExpired:
            _sync_sandbox_to_project(sandbox, self._project_dir)
            return [TestErrorEvent(
                task_id=event.task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={"error_message": "pytest timed out after 600s", "exit_code": -1},
            )]
        except Exception as e:
            _sync_sandbox_to_project(sandbox, self._project_dir)
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

        # Sync all modified/new files from sandbox back to project (not just tests/)
        synced = _sync_sandbox_to_project(sandbox, self._project_dir)

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
                         "failures": failures,
                         "synced_files": synced},
            )]
        return [TestPassedEvent(
            task_id=event.task_id, from_agent=AgentName.TESTER,
            to_agent=AgentName.CONTROLLER,
            payload={"total": total, "passed": passed, "duration": 0, "coverage": 0.0,
                     "synced_files": synced},
        )]
