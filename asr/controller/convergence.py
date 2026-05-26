from __future__ import annotations

import asyncio
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

    async def run(self, spec: Specification, task_id: str | None = None,
                  progress_callback=None) -> ConvergenceResult:
        task_id = task_id or str(uuid.uuid4())
        iteration = 0
        result = ConvergenceResult(state=ConvergenceState.INIT)

        prev_failures: list[dict] = []
        prev_feedback: list[str] = []
        before_count = 0

        while iteration < self._config.convergence.max_iterations:
            iteration += 1
            result.iterations = iteration

            repair_events = await self._repairing_phase(task_id, prev_failures, prev_feedback)
            result.events.extend(repair_events)
            if progress_callback:
                patches = sum(1 for e in repair_events if e.type == EventType.PATCH_APPLIED and e.payload.get("success"))
                py_count = len(list(self._project_dir.rglob("*.py")))
                total_lines = sum(len(f.read_text().split("\n")) for f in self._project_dir.rglob("*.py") if "__pycache__" not in str(f))
                detail = f"patches={patches} files={py_count} lines={total_lines}"
                if prev_failures:
                    detail += f" fixing={len(prev_failures)}"
                elif prev_feedback:
                    detail += f" gaps={len(prev_feedback)}"
                else:
                    detail += " init"
                progress_callback(iteration, 0, "BUILDING", False, False, detail)

            test_events = await self._testing_phase(task_id)
            result.events.extend(test_events)

            test_failed = any(e.type == EventType.TEST_FAILED for e in test_events)
            test_error = any(e.type in (EventType.TEST_ERROR, EventType.ERROR_OCCURRED) for e in test_events)
            after_count = _count_failures(test_events)

            if progress_callback:
                total_tests = sum(e.payload.get("total", 0) for e in test_events if hasattr(e, 'payload'))
                passed_tests = sum(e.payload.get("passed", 0) for e in test_events if hasattr(e, 'payload'))
                failed_names = []
                for e in test_events:
                    if e.type == EventType.TEST_FAILED:
                        for f in e.payload.get("failures", [])[:3]:
                            failed_names.append(f.get("nodeid", "?").split("::")[-1][:30])
                detail = f"passed={passed_tests}/{total_tests}"
                if failed_names:
                    detail += f" fail={','.join(failed_names)}"
                progress_callback(iteration, after_count, "TESTING", test_failed, test_error, detail)

            if after_count > before_count and self._rollback_entries:
                snapshotted = {e.file_path for e in self._rollback_entries}
                for entry in reversed(self._rollback_entries):
                    target = self._project_dir / entry.file_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(entry.original_content)
                for py_file in self._project_dir.rglob("*.py"):
                    if "test_" in py_file.name or "__pycache__" in str(py_file):
                        continue
                    rel = str(py_file.relative_to(self._project_dir))
                    if rel not in snapshotted:
                        py_file.unlink(missing_ok=True)
            self._rollback_entries.clear()
            before_count = after_count

            if test_error:
                test_failed = True

            if not test_failed and not test_error:
                analysis_events = await self._analyzing_phase(task_id, test_events)
                result.events.extend(analysis_events)
                spec_aligned = any(e.type == EventType.SPEC_ALIGNED for e in analysis_events)
                if progress_callback:
                    gap_details = []
                    for e in analysis_events:
                        if e.type == EventType.ANALYZER_FEEDBACK:
                            gap_details.extend(e.payload.get("findings", [])[:2])
                        elif e.type == EventType.SPEC_DIFF_FOUND:
                            for k in ("missing_features", "logic_issues", "constraint_violations"):
                                items = e.payload.get(k, [])[:1]
                                gap_details.extend(items)
                    detail = "aligned" if spec_aligned else f"gaps={len(gap_details)}"
                    if gap_details:
                        detail += f" {gap_details[0][:40]}"
                    progress_callback(iteration, after_count, "ANALYZING", False, not spec_aligned, detail)
            else:
                analysis_events = []
                spec_aligned = False
            if not test_failed and not test_error and spec_aligned:
                self._emit_converged(task_id, iteration, result)
                return result

            prev_failures = []
            for evt in test_events:
                if evt.type == EventType.TEST_FAILED:
                    prev_failures.extend(evt.payload.get("failures", []))
            prev_feedback = []
            for evt in analysis_events:
                if evt.type == EventType.ANALYZER_FEEDBACK:
                    prev_feedback.extend(evt.payload.get("findings", []))

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
        for evt in self._event_store.get_task_events(task_id):
            if evt.type in (EventType.TEST_FAILED, EventType.TEST_PASSED, EventType.TEST_ERROR):
                if evt.event_id not in {e.event_id for e in events}:
                    events.append(evt)
        return events

    async def _analyzing_phase(self, task_id: str, test_events: list[Event]) -> list[Event]:
        events: list[Event] = []
        test_summary = self._extract_test_summary(test_events)
        spec_diff = AnalyzeRequestedEvent(
            task_id=task_id, from_agent=AgentName.CONTROLLER, to_agent=AgentName.ANALYZER,
            payload={"project_path": str(self._project_dir), "test_summary": test_summary},
        )
        if self._analyzer:
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

        if self._builder:
            for py_file in self._project_dir.rglob("*.py"):
                if "test_" not in py_file.name and "__pycache__" not in str(py_file):
                    try:
                        content = py_file.read_text()
                    except Exception:
                        continue
                    self._rollback_entries.append(PatchEntry(
                        file_path=str(py_file.relative_to(self._project_dir)),
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
                    summary = evt.payload.get("summary", {})
                    if summary.get("files", 0) > 0:
                        applied = PatchAppliedEvent(
                            task_id=task_id, from_agent=AgentName.BUILDER,
                            to_agent=AgentName.CONTROLLER,
                            payload={"file_path": "", "success": True, "error": None},
                        )
                        self._event_store.write_event(applied)
                        events.append(applied)
                    self._patch_history.append(evt)
                    self._patch_lineage.append({
                        "seq": len(self._patch_lineage) + 1,
                        "file": "*", "risk": summary,
                    })
        return events

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
        results = await agent.process(event)
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
        inbox_dir = Path(".runtime/inbox") / str(event.to_agent.value)
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
