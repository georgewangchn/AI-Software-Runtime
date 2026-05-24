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
    TaskCreatedEvent,
    TestStartedEvent,
    TestFailedEvent,
    TestPassedEvent,
    TestErrorEvent,
    SpecDiffFoundEvent,
    SpecAlignedEvent,
    PatchGeneratedEvent,
    PatchAppliedEvent,
    PatchFailedEvent,
    PatchRolledBackEvent,
    AnalyzerFeedbackEvent,
    ConvergedEvent,
    StuckEvent,
    ErrorOccurredEvent,
    ConvergenceIterationEvent,
)
from asr.events.store import EventStore
from asr.spec.models import Specification
from asr.agents.base import BaseAgent
from asr.patch.diff import PatchEngine, PatchEntry
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
        self._patch_engine = PatchEngine()
        self._patch_history: list[PatchGeneratedEvent] = []
        self._rollback_entries: list[PatchEntry] = []
        self._patch_lineage: list[dict] = []

    async def run(self, spec: Specification, task_id: str | None = None,
                  progress_callback=None) -> ConvergenceResult:
        task_id = task_id or str(uuid.uuid4())
        iteration = 0
        result = ConvergenceResult(state=ConvergenceState.INIT)

        task_event = TaskCreatedEvent(
            task_id=task_id, from_agent=AgentName.CONTROLLER, to_agent=AgentName.BUILDER,
            payload={"spec": spec.model_dump(), "project_path": str(self._project_dir),
                     "max_iterations": self._config.convergence.max_iterations},
        )
        self._write_and_log(task_event, result)

        prev_failures: list[dict] = []
        prev_feedback: list[str] = []
        before_count = 0

        while iteration < self._config.convergence.max_iterations:
            iteration += 1
            result.iterations = iteration

            repair_events = await self._repairing_phase(task_id, prev_failures, prev_feedback)
            result.events.extend(repair_events)
            if progress_callback:
                progress_callback(iteration, 0, "BUILDING", False, False)

            test_events = await self._testing_phase(task_id)
            result.events.extend(test_events)

            test_failed = any(e.type == EventType.TEST_FAILED for e in test_events)
            test_error = any(e.type == EventType.TEST_ERROR for e in test_events)
            after_count = _count_failures(test_events)

            if progress_callback:
                progress_callback(iteration, after_count, "TESTING", test_failed, test_error)

            if before_count > 0 and after_count > before_count and self._rollback_entries:
                self._patch_engine.rollback(self._rollback_entries)
                self._rollback_entries.clear()
            before_count = after_count

            if test_error:
                test_failed = True

            analysis_events = await self._analyzing_phase(task_id, test_events)
            result.events.extend(analysis_events)

            spec_aligned = any(e.type == EventType.SPEC_ALIGNED for e in analysis_events)
            if progress_callback:
                progress_callback(iteration, after_count, "ANALYZING", False, not spec_aligned)
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
        spec_diff = SpecDiffFoundEvent(
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

        if self._builder and (failures or feedback):
            patch_request = PatchGeneratedEvent(
                task_id=task_id, from_agent=AgentName.CONTROLLER, to_agent=AgentName.BUILDER,
                payload={"failures": failures, "feedback": feedback, "project_path": str(self._project_dir)},
            )
            result_events = await self._invoke_agent(self._builder, patch_request, task_id, "repairing")
            for evt in result_events:
                events.append(evt)
                if evt.type == EventType.PATCH_GENERATED:
                    has_failures = bool(evt.payload.get("failures") if isinstance(evt.payload, dict) else False)
                    if has_failures:
                        self._patch_history.append(evt)
                    diff_text = evt.payload.get("diff_text", "")
                    file_path = evt.payload.get("file_path", "")
                    if diff_text:
                        original = self._read_file_safe(file_path)
                        if original is not None:
                            result = self._patch_engine.apply_single(diff_text, original)
                        else:
                            result = self._patch_engine.apply_single(diff_text, "")
                            file_path = file_path or "main.py"
                        applied = PatchAppliedEvent(
                            task_id=task_id, from_agent=AgentName.BUILDER,
                            to_agent=AgentName.CONTROLLER,
                            payload={"file_path": file_path, "success": result.success,
                                     "error": result.error if not result.success else None},
                        )
                        self._event_store.write_event(applied)
                        events.append(applied)
                        if result.success and result.content:
                            target = self._resolve_target(file_path)
                            if target and "test_" not in file_path:
                                if original:
                                    self._rollback_entries.append(PatchEntry(
                                        file_path=file_path, diff_text=diff_text,
                                        original_content=original,
                                    ))
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_text(result.content)

                        if result.success:
                            risk = self._compute_risk(diff_text)
                            self._patch_lineage.append({
                                "seq": len(self._patch_lineage) + 1,
                                "file": file_path, "risk": risk,
                            })
            if self._use_decoupled and not events:
                await asyncio.sleep(0.1)
                for evt in self._event_store.get_task_events(task_id):
                    if evt.type in (EventType.PATCH_APPLIED, EventType.PATCH_FAILED, EventType.PATCH_GENERATED):
                        if evt.event_id not in {e.event_id for e in events}:
                            events.append(evt)
            return events

        if failures:
            patch_event = PatchGeneratedEvent(
                task_id=task_id, from_agent=AgentName.CONTROLLER, to_agent=AgentName.BUILDER,
                payload={"failures": failures, "project_path": str(self._project_dir)},
            )
            self._event_store.write_event(patch_event)
            events.append(patch_event)
            self._patch_history.append(patch_event)
        await asyncio.sleep(0.1)
        for evt in self._event_store.get_task_events(task_id):
            if evt.type in (EventType.PATCH_APPLIED, EventType.PATCH_FAILED, EventType.PATCH_GENERATED):
                if evt.event_id not in {e.event_id for e in events}:
                    events.append(evt)
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

    def _compute_risk(self, diff_text: str) -> dict:
        lines = diff_text.split("\n")
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        files_touched = max(1, len([l for l in lines if l.startswith("--- a/")]) )

        bypass_detected = any(p in diff_text for p in [
            "except:", "pass", "if DEBUG:", "return expected",
            "mock(", "@pytest.mark.skip",
        ])

        score = min(100, added * 2 + removed * 3 + files_touched * 10 + (25 if bypass_detected else 0))
        return {
            "score": score,
            "lines_added": added, "lines_removed": removed,
            "files_touched": files_touched,
            "bypass_detected": bypass_detected,
        }

    def lineage_summary(self) -> list[dict]:
        return list(self._patch_lineage)

    def _detect_stable_diff(self) -> bool:
        threshold = self._config.convergence.stable_diff_threshold
        if len(self._patch_history) < threshold:
            return False
        diffs = [p.payload.get("diff_text", "") if isinstance(p.payload, dict) else ""
                 for p in self._patch_history[-threshold:]]
        return len(set(diffs)) == 1 and all(diffs)

    def _detect_patch_oscillation(self) -> bool:
        threshold = self._config.convergence.patch_oscillation_threshold
        if len(self._patch_history) < threshold:
            return False
        diffs = [p.payload.get("diff_text", "") if isinstance(p.payload, dict) else ""
                 for p in self._patch_history[-threshold:]]
        unique = set(diffs)
        return len(unique) == 2 and len(diffs) >= 3


def _count_failures(events: list[Event]) -> int:
    count = 0
    for evt in events:
        if evt.type == EventType.TEST_FAILED:
            payload = evt.payload if isinstance(evt.payload, dict) else {}
            count += payload.get("failed", len(payload.get("failures", [])))
        elif evt.type == EventType.TEST_ERROR:
            count += 1
    return count


_EXPECTED_TYPES: dict[str, set[EventType]] = {
    "testing": {EventType.TEST_FAILED, EventType.TEST_PASSED, EventType.TEST_ERROR},
    "analyzing": {EventType.SPEC_ALIGNED, EventType.SPEC_DIFF_FOUND, EventType.ANALYZER_FEEDBACK},
    "repairing": {EventType.PATCH_GENERATED, EventType.PATCH_APPLIED, EventType.PATCH_FAILED},
    "generating": {EventType.CODE_GENERATED},
}
