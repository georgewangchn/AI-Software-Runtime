from __future__ import annotations

import asyncio
import difflib
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from asr.config.models import ASRConfig
from asr.events.models import (
    Event,
    EventType,
    AgentName,
    TestStartedEvent,
    TestFailedEvent,
    TestPassedEvent,
    TestErrorEvent,
    SpecDiffFoundEvent,
    SpecAlignedEvent,
    PatchRequestedEvent,
    PatchGeneratedEvent,
    PatchAppliedEvent,
    PatchFailedEvent,
    AnalyzeRequestedEvent,
    AnalyzerFeedbackEvent,
    ConvergedEvent,
    StuckEvent,
    ErrorOccurredEvent,
    ConvergenceIterationEvent,
)
from asr.events.store import EventStore
from asr.spec.models import Specification
from asr.agents.base import BaseAgent
from asr.patch.diff import PatchEntry
from asr.logger import ASRLogger


class ConvergenceState(str, Enum):
    INIT = "init"
    GENERATING = "generating"
    TESTING = "testing"
    ANALYZING = "analyzing"
    REPAIRING = "repairing"
    CONVERGED = "converged"
    STUCK = "stuck"


@dataclass
class ConvergenceResult:
    state: ConvergenceState
    iterations: int = 0
    events: list[Event] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


class ASRController:
    def __init__(
        self,
        config: ASRConfig,
        event_store: EventStore,
        project_dir: Path,
        builder: BaseAgent | None = None,
        tester: BaseAgent | None = None,
        analyzer: BaseAgent | None = None,
        use_decoupled_a2a: bool = False,
        logger: ASRLogger | None = None,
    ):
        self._config = config
        self._event_store = event_store
        self._project_dir = project_dir
        self._builder = builder
        self._tester = tester
        self._analyzer = analyzer
        self._use_decoupled = use_decoupled_a2a
        self._logger = logger
        self._patch_history: list[PatchGeneratedEvent] = []
        self._rollback_entries: list[PatchEntry] = []
        self._patch_lineage: list[dict] = []
        self._builder_counter = 0  # Counter for tracking builder invocations

    async def run(self, spec: Specification, task_id: str | None = None,
                  progress_callback=None) -> ConvergenceResult:
        task_id = task_id or str(uuid.uuid4())
        iteration = 0
        result = ConvergenceResult(state=ConvergenceState.INIT)

        prev_failures: list[dict] = []
        prev_feedback: list[str] = []
        before_count = 0
        prev_test_count = 0

        while iteration < self._config.convergence.max_iterations:
            iteration += 1
            result.iterations = iteration

            if iteration > 1 and not prev_failures and not prev_feedback:
                repair_events = []
            else:
                repair_events = await self._repairing_phase(task_id, prev_failures, prev_feedback)
                # Increment builder counter when repair phase generates patches
                if any(e.type == EventType.PATCH_GENERATED for e in repair_events):
                    self._builder_counter += 1
            result.events.extend(repair_events)
            if progress_callback:
                patches = sum(1 for e in repair_events if e.type == EventType.PATCH_APPLIED and e.payload.get("success"))
                py_count = len([f for f in self._project_dir.rglob("*.py") if not any(p in str(f) for p in ("__pycache__", ".asr_sandbox", ".runtime", ".pytest_cache", ".git/", ".omo"))])
                total_lines = 0
                for f in self._project_dir.rglob("*.py"):
                    if any(p in str(f) for p in ("__pycache__", ".asr_sandbox", ".runtime", ".pytest_cache", ".git/", ".omo")):
                        continue
                    try:
                        total_lines += len(f.read_text().split("\n"))
                    except Exception:
                        continue
                detail = f"补丁:{patches} 文件:{py_count} 代码行:{total_lines}"
                if prev_failures:
                    detail += f" 修复{len(prev_failures)}个失败"
                elif prev_feedback:
                    detail += f" 偏差:{len(prev_feedback)}"
                else:
                    detail += " 初始生成"
                progress_callback(iteration, 0, "BUILDING", False, False, detail)

            test_events = await self._testing_phase(task_id)
            result.events.extend(test_events)

            test_failed = any(e.type == EventType.TEST_FAILED for e in test_events)
            test_error = any(e.type in (EventType.TEST_ERROR, EventType.ERROR_OCCURRED) for e in test_events)
            after_count = _count_failures(test_events)

            current_test_count = sum(e.payload.get("total", 0) for e in test_events if hasattr(e, 'payload'))
            if current_test_count != prev_test_count:
                before_count = after_count
                prev_test_count = current_test_count

            if progress_callback:
                total_tests = sum(e.payload.get("total", 0) for e in test_events if hasattr(e, 'payload'))
                passed_tests = sum(e.payload.get("passed", 0) for e in test_events if hasattr(e, 'payload'))
                failed_names = []
                for e in test_events:
                    if e.type == EventType.TEST_FAILED:
                        for f in e.payload.get("failures", [])[:3]:
                            failed_names.append(f.get("nodeid", "?").split("::")[-1][:30])
                detail = f"通过:{passed_tests}/{total_tests}"
                if failed_names:
                    detail += f" 失败:{','.join(failed_names)}"
                progress_callback(iteration, after_count, "TESTING", test_failed, test_error, detail)

            if before_count > 0 and after_count > before_count and after_count > before_count * 1.5 and self._rollback_entries:
                snapshotted = {e.file_path for e in self._rollback_entries}
                for entry in reversed(self._rollback_entries):
                    target = self._project_dir / entry.file_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(entry.original_content)
                for f in self._project_dir.rglob("*"):
                    if f.is_dir():
                        continue
                    if any(p in str(f) for p in ("__pycache__", ".asr_sandbox", ".git/", ".runtime", ".pytest_cache")):
                        continue
                    rel = str(f.relative_to(self._project_dir))
                    if rel not in snapshotted:
                        f.unlink(missing_ok=True)
            self._rollback_entries.clear()
            before_count = after_count

            if test_error:
                test_failed = True

            # Determine if we should force analyzer (periodic code review every 3 builder calls)
            force_analyze = (self._builder_counter > 0 and self._builder_counter % 3 == 0)
            analysis_events = await self._analyzing_phase(task_id, test_events, force_analyze)
            result.events.extend(analysis_events)
            # spec_aligned only if there's a SPEC_ALIGNED event AND NO contradictory
            # analyzer_feedback or spec_diff_found in the same round — otherwise it's
            # a false positive (analyzer said ALL CLEAR while also reporting issues)
            spec_aligned = (
                any(e.type == EventType.SPEC_ALIGNED for e in analysis_events)
                and not any(e.type in (EventType.ANALYZER_FEEDBACK, EventType.SPEC_DIFF_FOUND) for e in analysis_events)
            )
            if progress_callback:
                gap_details = []
                for e in analysis_events:
                    if e.type == EventType.ANALYZER_FEEDBACK:
                        gap_details.extend(e.payload.get("findings", [])[:2])
                    elif e.type == EventType.SPEC_DIFF_FOUND:
                        for k in ("missing_features", "logic_issues", "constraint_violations"):
                            items = e.payload.get(k, [])[:1]
                            gap_details.extend(items)
                detail = "规格一致" if spec_aligned else f"偏差:{len(gap_details)}"
                if gap_details:
                    detail += f" {gap_details[0][:40]}"
                progress_callback(iteration, after_count, "ANALYZING", False, not spec_aligned, detail)
            if not test_failed and not test_error and spec_aligned:
                self._convergence_streak = getattr(self, '_convergence_streak', 0) + 1
                if self._convergence_streak >= 3:  # require 3 consecutive aligned rounds
                    self._emit_converged(task_id, iteration, result)
                    return result
            else:
                self._convergence_streak = 0

            prev_failures = []
            for evt in test_events:
                if evt.type == EventType.TEST_FAILED:
                    for f in evt.payload.get("failures", []):
                        if f.get("nodeid") != "no_code":
                            prev_failures.append(f)
            current_feedback = []
            for evt in analysis_events:
                if evt.type == EventType.ANALYZER_FEEDBACK:
                    findings = evt.payload.get("findings", [])
                    current_feedback.extend(findings)
                    high_count = evt.payload.get("high_severity_count", 0)
                    recommendation = evt.payload.get("recommendation", "")
                    if high_count > 0:
                        current_feedback.insert(0, f"[PRIORITY] {high_count} high-severity issues — fix these first")
                    if recommendation and recommendation != "Fix the identified issues":
                        current_feedback.insert(0, f"[STRATEGY] {recommendation}")
            for evt in test_events:
                if evt.type in (EventType.TEST_ERROR, EventType.ERROR_OCCURRED):
                    error_msg = evt.payload.get("error_message", "")
                    if error_msg:
                        current_feedback.append(f"[COMPILE_ERROR] {error_msg}")
            # Collect Builder errors from repair phase (e.g. fake-death detection)
            builder_fakedeath = False
            for evt in repair_events:
                if evt.type == EventType.ERROR_OCCURRED:
                    error_msg = evt.payload.get("error_message", "")
                    retry_hint = evt.payload.get("retry_hint", "")
                    if error_msg:
                        tag = "[BUILDER_FAKEDEATH]" if retry_hint == "reset_session" else "[BUILDER_ERROR]"
                        current_feedback.append(f"{tag} {error_msg}")
                    if retry_hint == "reset_session":
                        builder_fakedeath = True
            # Fake-death: Builder made zero changes despite having failures/feedback.
            # Force test_failed to prevent false convergence when tests happen to pass.
            # Also inject a completeness check so the fresh Builder session knows to
            # re-read DESIGN.md and verify all structures exist (not just fix tests).
            if builder_fakedeath and (prev_failures or prev_feedback):
                test_failed = True
                current_feedback.append(
                    "[COMPLETENESS] Builder session was reset due to context overflow. "
                    "在新的会话中，首先重新读取 DESIGN.md，逐项检查所有描述的结构、文件、"
                    "目录、Schema 是否都已完整创建——而不仅仅是修复测试失败。"
                )
            for evt in analysis_events:
                if evt.type == EventType.ERROR_OCCURRED:
                    error_msg = evt.payload.get("error_message", "")
                    if error_msg:
                        current_feedback.append(f"[ANALYZER_ERROR] {error_msg}")
            if current_feedback:
                current_feedback[-1] = f"{current_feedback[-1]} (迭代{iteration})"
                prev_feedback = (prev_feedback + current_feedback)[-30:]

            self._write_and_log(ConvergenceIterationEvent(
                task_id=task_id, from_agent=AgentName.CONTROLLER, to_agent=AgentName.SYSTEM,
                payload={"iteration": iteration, "errors_remaining": after_count,
                         "phase": "REPAIRING", "detail": "continuing"},
            ), result)

        self._emit_stuck(task_id, iteration, "max_iterations", [], result)
        return result

    async def _testing_phase(self, task_id: str) -> list[Event]:
        events: list[Event] = []
        test_started = TestStartedEvent(
            task_id=task_id, from_agent=AgentName.CONTROLLER, to_agent=AgentName.TESTER,
            payload={"test_paths": [str(self._project_dir)]},
        )
        if self._tester:
            result_events = await self._invoke_agent(self._tester, test_started, task_id, "testing")
            if result_events:
                return result_events
        self._event_store.write_event(test_started)
        events.append(test_started)
        await asyncio.sleep(0.1)
        has_results = False
        for evt in self._event_store.get_task_events(task_id):
            if evt.type in (EventType.TEST_FAILED, EventType.TEST_PASSED, EventType.TEST_ERROR):
                has_results = True
                if evt.event_id not in {e.event_id for e in events}:
                    events.append(evt)
        if not has_results:
            events.append(TestErrorEvent(
                task_id=task_id, from_agent=AgentName.TESTER,
                to_agent=AgentName.CONTROLLER,
                payload={"error_message": "No tester agent configured or no test results found", "exit_code": -1},
            ))
        return events

    async def _analyzing_phase(self, task_id: str, test_events: list[Event], force_analyze: bool = False) -> list[Event]:
        events: list[Event] = []
        test_summary = self._extract_test_summary(test_events)
        spec_diff = AnalyzeRequestedEvent(
            task_id=task_id, from_agent=AgentName.CONTROLLER, to_agent=AgentName.ANALYZER,
            payload={"project_path": str(self._project_dir), "test_summary": test_summary},
        )
        # Force analyzer to run every 3 builder invocations (periodic code review)
        # or when there are test failures
        if self._analyzer and (force_analyze or any(e.type == EventType.TEST_FAILED for e in test_events)):
            result_events = await self._invoke_agent(self._analyzer, spec_diff, task_id, "analyzing")
            if result_events:
                events.extend(result_events)

        if not events:
            self._event_store.write_event(spec_diff)
            events.append(spec_diff)
            await asyncio.sleep(0.1)
        for evt in self._event_store.get_task_events(task_id):
            if evt.type in (EventType.SPEC_ALIGNED, EventType.SPEC_DIFF_FOUND, EventType.ANALYZER_FEEDBACK):
                if evt.event_id not in {e.event_id for e in events}:
                    events.append(evt)
        return events

    async def _repairing_phase(
        self, task_id: str, failures: list[dict], feedback: list[str]
    ) -> list[Event]:
        events: list[Event] = []

        # ── Diagnostic: snapshot project state before Builder runs ──
        import sys as _sys
        py_files_before = [f for f in self._project_dir.rglob("*.py")
                           if not any(p in str(f) for p in ("__pycache__", ".asr_sandbox", ".runtime", ".pytest_cache", ".git/", ".omo"))]
        py_dirs = sorted(set(f.parent.relative_to(self._project_dir) for f in py_files_before))
        print(f"[convergence] REPAIRING iter={self._iteration_count if hasattr(self,'_iteration_count') else '?'} "
              f"pre-Builder: {len(py_files_before)} py files in project={self._project_dir} "
              f"top_dirs={[str(d) for d in py_dirs[:8]]}", file=_sys.stderr)

        if self._builder:
            skip_patterns = ("__pycache__", ".asr_sandbox", ".git/", ".runtime", ".pytest_cache")
            for f in self._project_dir.rglob("*"):
                if f.is_dir():
                    continue
                if any(p in str(f) for p in skip_patterns):
                    continue
                try:
                    content = f.read_text()
                except Exception:
                    continue
                self._rollback_entries.append(PatchEntry(
                    file_path=str(f.relative_to(self._project_dir)),
                    diff_text="", original_content=content,
                ))

            patch_request = PatchRequestedEvent(
                task_id=task_id, from_agent=AgentName.CONTROLLER, to_agent=AgentName.BUILDER,
                payload={"failures": failures, "feedback": feedback, "project_path": str(self._project_dir)},
            )
            result_events = await self._invoke_agent(self._builder, patch_request, task_id, "repairing")
            for evt in result_events:
                events.append(evt)
                if evt.type == EventType.PATCH_GENERATED:
                    self._patch_history.append(evt)

            snapshotted = {e.file_path: e.original_content for e in self._rollback_entries}
            changed = 0
            combined_diff: list[str] = []

            for entry in self._rollback_entries:
                target = self._project_dir / entry.file_path
                if not target.exists():
                    continue
                current = target.read_text()
                if current == entry.original_content:
                    continue
                changed += 1
                diff = list(difflib.unified_diff(
                    entry.original_content.splitlines(keepends=True),
                    current.splitlines(keepends=True),
                    fromfile=f"a/{entry.file_path}",
                    tofile=f"b/{entry.file_path}",
                ))
                combined_diff.extend(diff)

            for f in self._project_dir.rglob("*"):
                if f.is_dir():
                    continue
                if any(p in str(f) for p in ("__pycache__", ".asr_sandbox", ".git/", ".runtime", ".pytest_cache")):
                    continue
                rel = str(f.relative_to(self._project_dir))
                if rel not in snapshotted:
                    changed += 1
                    try:
                        new_content = f.read_text()
                    except UnicodeDecodeError:
                        continue  # skip binary files
                    diff = list(difflib.unified_diff(
                        [], new_content.splitlines(keepends=True),
                        fromfile=f"a/{rel}",
                        tofile=f"b/{rel}",
                    ))
                    combined_diff.extend(diff)

            if changed > 0:
                diff_text = "".join(combined_diff)
                summary = _compute_diff_summary(diff_text)
                applied = PatchAppliedEvent(
                    task_id=task_id, from_agent=AgentName.BUILDER,
                    to_agent=AgentName.CONTROLLER,
                    payload={"file_path": "*", "success": True, "error": None},
                )
                self._event_store.write_event(applied)
                events.append(applied)
                if diff_text:
                    self._event_store.save_patch(task_id, diff_text, "*")
                self._patch_lineage.append({
                    "seq": len(self._patch_lineage) + 1,
                    "file": "*", "risk": summary,
                })
        return events

    _PHASE_TIMEOUT_MAP = {
        "repairing": "repair_timeout",
        "testing": "test_timeout",
        "analyzing": "analyze_timeout",
        "generating": "repair_timeout",
    }

    async def _invoke_agent(
        self, agent: BaseAgent | None, event: Event, task_id: str, phase: str
    ) -> list[Event]:
        if agent is None:
            return []
        if self._use_decoupled:
            self._write_to_inbox(event)
            await asyncio.sleep(0.2)
            results = []
            for evt in self._event_store.get_task_events(task_id):
                if evt.from_agent == agent.name and evt.event_id != event.event_id:
                    if evt.type in _EXPECTED_TYPES.get(phase, set()):
                        results.append(evt)
            return results
        timeout_attr = self._PHASE_TIMEOUT_MAP.get(phase, "test_timeout")
        timeout = getattr(self._config.convergence, timeout_attr, 3600)
        try:
            results = await asyncio.wait_for(
                agent.process(event),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return [ErrorOccurredEvent(
                task_id=task_id, from_agent=agent.name,
                to_agent=AgentName.CONTROLLER,
                payload={"agent": str(agent.name.value), "error_type": "TimeoutError",
                         "error_message": f"Agent {agent.name.value} timed out after {timeout}s",
                         "retry_hint": "retryable"},
            )]
        for evt in results:
            self._write_to_inbox(evt)
            self._event_store.write_event(evt)
        return results

    def _resolve_target(self, file_path: str) -> Path | None:
        if not file_path or "test_" in file_path:
            return None
        return self._project_dir / file_path

    def _read_file_safe(self, file_path: str) -> str | None:
        target = self._resolve_target(file_path)
        if target and target.exists():
            return target.read_text()
        return None

    def _extract_test_summary(self, test_events: list[Event]) -> dict:
        total = passed = failed = 0
        failures = []
        for evt in test_events:
            if evt.type == EventType.TEST_PASSED:
                total = evt.payload.get("total", total)
                passed = evt.payload.get("passed", passed)
            elif evt.type == EventType.TEST_FAILED:
                total = evt.payload.get("total", total)
                failed = evt.payload.get("failed", failed)
                failures = evt.payload.get("failures", [])
        return {"total": total, "passed": passed, "failed": failed, "failures": failures}

    def _write_and_log(self, event: Event, result: ConvergenceResult) -> None:
        self._event_store.write_event(event)
        result.events.append(event)

    def _write_to_inbox(self, event: Event) -> None:
        inbox_dir = self._event_store._inbox_dir / str(event.to_agent.value)
        inbox_dir.mkdir(parents=True, exist_ok=True)
        event_path = inbox_dir / f"{event.event_id}.json"
        tmp_path = inbox_dir / f"{event.event_id}.tmp"
        tmp_path.write_text(event.model_dump_json(indent=2))
        tmp_path.rename(event_path)

    def _emit_converged(self, task_id: str, iteration: int, result: ConvergenceResult) -> None:
        self._write_and_log(ConvergedEvent(
            task_id=task_id, from_agent=AgentName.CONTROLLER, to_agent=AgentName.SYSTEM,
            payload={"total_iterations": iteration, "final_test_results": {"passed": True},
                     "lineage": self.lineage_summary()},
        ), result)
        result.state = ConvergenceState.CONVERGED
        result.summary["lineage"] = self.lineage_summary()

    def _emit_stuck(self, task_id: str, iteration: int, reason: str,
                    test_events: list[Event], result: ConvergenceResult) -> None:
        self._write_and_log(StuckEvent(
            task_id=task_id, from_agent=AgentName.CONTROLLER, to_agent=AgentName.SYSTEM,
            payload={"reason": reason, "last_iteration": iteration,
                     "errors_remaining": len(test_events),
                     "lineage": self.lineage_summary()},
        ), result)
        result.state = ConvergenceState.STUCK
        result.summary["lineage"] = self.lineage_summary()

    def lineage_summary(self) -> list[dict]:
        return list(self._patch_lineage)


def _count_failures(events: list[Event]) -> int:
    count = 0
    for evt in events:
        if evt.type == EventType.TEST_FAILED:
            payload = evt.payload if isinstance(evt.payload, dict) else {}
            count += payload.get("failed", len(payload.get("failures", [])))
        elif evt.type in (EventType.TEST_ERROR, EventType.ERROR_OCCURRED):
            count += 1
    return count


_EXPECTED_TYPES: dict[str, set[EventType]] = {
    "testing": {EventType.TEST_FAILED, EventType.TEST_PASSED, EventType.TEST_ERROR},
    "analyzing": {EventType.SPEC_ALIGNED, EventType.SPEC_DIFF_FOUND, EventType.ANALYZER_FEEDBACK},
    "repairing": {EventType.PATCH_GENERATED, EventType.PATCH_APPLIED, EventType.PATCH_FAILED},
    "generating": {EventType.CODE_GENERATED},
}


def _compute_diff_summary(diff_text: str) -> dict:
    if not diff_text:
        return {"files": 0, "added": 0, "removed": 0, "bypass_detected": False, "risk_score": 0}
    lines = diff_text.split("\n")
    added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    files_touched = max(1, len([l for l in lines if l.startswith("--- a/") or l.startswith("+++ b/")]))
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
