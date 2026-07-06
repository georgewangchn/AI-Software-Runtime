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
    ConvergenceMetricsEvent,
    ConvergenceMetrics,
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
        # ── Control-theoretic metrics ──
        self._metrics_history: list = []  # list[ConvergenceMetrics]
        self._error_score_history: list[float] = []
        self._patch_fingerprints: list[str] = []  # SHA-256 of diffs
        self._failure_fingerprints: list[str] = []  # N1: SHA-256 of failure signatures
        self._repair_mode: str = "INITIAL"  # Phase 2: auto-switch repair mode
        self._pass_rate_history: list[float] = []  # ground-truth pass rate (PRIMARY signal)
        self._no_improvement_streak: int = 0  # circuit breaker counter
        self._prev_rollback_entries: list[PatchEntry] = []  # snapshot for REGRESSION_RECOVERY
        # ── #1 fix: best snapshot for REGRESSION_RECOVERY ──
        self._best_snapshot: dict | None = None  # {"iteration", "test_pass_rate", "rollback_entries"}
        # ── #6 fix: hysteresis for mode switching ──
        self._trend_history: list[str] = []
        self._stalled_streak: int = 0
        self._regressing_streak: int = 0
        self._improving_streak: int = 0

        # ── #3 fix: notify Builder after patch rejection ──
        self._last_patch_rejection: tuple[int, str] | None = None  # (iteration, reason) from last rejected patch

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
            self._current_iteration = iteration  # for repairing_phase

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

            # FIX (Problem C): inline rollback removed — was conflicting with
            # REGRESSION_RECOVERY. Now _compute_metrics sees the real post-Builder
            # state, and REGRESSION_RECOVERY handles regressions properly.
            # Save a copy for REGRESSION_RECOVERY mode (next iteration may need to rollback)
            self._prev_rollback_entries = list(self._rollback_entries)
            self._rollback_entries.clear()
            before_count = after_count

            if test_error:
                test_failed = True

            # Determine if we should force analyzer (periodic code review every 3 builder calls)
            force_analyze = (self._builder_counter > 0 and self._builder_counter % 3 == 0)
            # N2: always force analyzer in FINAL_VERIFICATION mode
            if self._repair_mode == "FINAL_VERIFICATION":
                force_analyze = True
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
            # N2: FINAL_VERIFICATION — if tests pass but no analyzer ran this round,
            # switch to FINAL_VERIFICATION mode to force a full analysis before converging
            elif not test_failed and not test_error and not spec_aligned and not force_analyze:
                # Tests pass but analyzer didn't run (no SPEC_ALIGNED).
                # Force analyzer next round before declaring convergence.
                self._repair_mode = "FINAL_VERIFICATION"
                self._logger.log(
                    "INFO",
                    f"RepairMode → FINAL_VERIFICATION: tests pass but needs analyzer confirmation "
                    f"(iter={iteration})",
                    "controller"
                )
                self._convergence_streak = 0
            # FIX (P0-2): FINAL_VERIFICATION + Analyzer found issues → exit to repair mode.
            # Previously: FINAL_VERIFICATION had no exit — if Analyzer kept finding
            # issues, Builder was told "don't modify code" every round → dead loop
            # until max_iterations. Now: if Analyzer ran and found issues, switch
            # to SPEC_COMPLETION (for missing features) or TEST_FIX (otherwise).
            elif (not test_failed and not test_error and not spec_aligned
                  and force_analyze and self._repair_mode == "FINAL_VERIFICATION"):
                has_missing = any(
                    e.type == EventType.SPEC_DIFF_FOUND
                    and len(e.payload.get("missing_features", [])) > 0
                    for e in analysis_events
                )
                self._repair_mode = "SPEC_COMPLETION" if has_missing else "TEST_FIX"
                self._logger.log(
                    "INFO",
                    f"RepairMode: FINAL_VERIFICATION → {self._repair_mode} "
                    f"(Analyzer found issues, tests pass but spec not aligned)",
                    "controller"
                )
                self._convergence_streak = 0
            else:
                self._convergence_streak = 0

            # ── Control-theoretic: compute metrics, switch mode, build feedback ──
            # Step 1: collect this iteration's failures (for next iteration's feedback)
            this_iter_failures = []
            for evt in test_events:
                if evt.type == EventType.TEST_FAILED:
                    for f in evt.payload.get("failures", []):
                        if f.get("nodeid") != "no_code":
                            this_iter_failures.append(f)

            # Step 2: compute metrics (uses ground-truth test results as primary signal)
            metrics = self._compute_metrics(
                iteration, test_events, analysis_events,
                repair_events, this_iter_failures,
            )
            self._emit_metrics(task_id, metrics, result)

            # Step 3: circuit breaker — stop if no meaningful progress
            cfg = self._config.convergence
            # Circuit breaker: stop if pass_rate is flat or decreasing.
            # FIX (Problem A): previous code used `< prev + 0.05` which treated
            # "improving by 4%" as "no improvement", causing premature stuck.
            # Correct: only count as no-improvement if pass_rate did NOT increase.
            if len(self._pass_rate_history) >= 2:
                if self._pass_rate_history[-1] <= self._pass_rate_history[-2]:
                    self._no_improvement_streak += 1
                else:
                    self._no_improvement_streak = 0
            circuit_threshold = getattr(cfg, 'circuit_breaker_stagnant_iters', 6)
            if self._no_improvement_streak >= circuit_threshold:
                self._logger.log("WARN", f"Circuit breaker: no improvement in {self._no_improvement_streak} iters", "controller")
                # Save state for human review
                import json, time as _time
                state_dir = self._project_dir / self._config.runtime.state_dir
                state_dir.mkdir(parents=True, exist_ok=True)
                snapshot = {
                    "task_id": task_id or "unknown",
                    "stopped_at": _time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "iteration": iteration,
                    "test_pass_rate": metrics.test_pass_rate,
                    "trend": metrics.trend,
                    "error_score": metrics.error_score,
                    "no_improvement_streak": self._no_improvement_streak,
                    "repair_mode": self._repair_mode,
                    "test_failed_count": metrics.test_failed_count,
                    "test_error_count": metrics.test_error_count,
                    "hint": "ASR could not converge. Review the project state and either adjust the spec or manually fix.",
                }
                snap_path = state_dir / f"stuck_{task_id or 'unknown'}_{iteration}.json"
                with open(snap_path, 'w') as sf:
                    json.dump(snapshot, sf, indent=2, ensure_ascii=False)
                self._logger.log("INFO", f"Human-in-the-loop: state saved to {snap_path}", "controller")
                self._emit_stuck(task_id, iteration, "circuit_breaker_no_improvement", test_events, result)
                return result

            # Step 4: mode switching (uses metrics.trend based on test_pass_rate)
            self._check_and_switch_mode(metrics, task_id, result)

            # Step 5: build feedback for next iteration's Builder
            current_feedback = []
            current_feedback.append(
                f"[REPAIR_MODE] {self._repair_mode} "
                f"(iteration {iteration}, pass_rate={metrics.test_pass_rate:.2f}, trend={metrics.trend})"
            )
            # Also append mode transition history (last 3 modes) so Builder can see the pattern
            if hasattr(self, '_mode_history'):
                recent_modes = [m for m, _ in self._mode_history[-3:]]
                if len(recent_modes) >= 2 and recent_modes[-1] != recent_modes[-2]:
                    current_feedback.append(
                        f"[MODE_HISTORY] {' → '.join(recent_modes)}"
                    )
            else:
                self._mode_history = []

            # Move prev_failures update to use this_iter_failures
            prev_failures = this_iter_failures

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
                # P4 fix: reduce noise — keep only last 15 items (was 30).
                # FIX (P1): mode_changed detection was broken — _mode_history only
                # records actual transitions, so after 2+ transitions, comparing
                # its last two entries always showed a change even when mode was
                # stable. Track previous mode directly instead.
                prev_mode = getattr(self, '_prev_mode_for_feedback', None)
                mode_changed = prev_mode is not None and prev_mode != self._repair_mode
                self._prev_mode_for_feedback = self._repair_mode
                if mode_changed:
                    # Keep only high-priority items from prev_feedback
                    prev_feedback = [fb for fb in prev_feedback
                                     if fb.startswith("[PRIORITY]") or fb.startswith("[COMPILE_ERROR]")]
                prev_feedback = (prev_feedback + current_feedback)[-15:]

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
        # Compute diff from pre-Builder state for diff-only analysis
        analysis_diff = ""
        prev_entries = getattr(self, '_prev_rollback_entries', None) or []
        if prev_entries:
            import difflib as _difflib
            diff_lines = []
            for entry in prev_entries:
                target = self._project_dir / entry.file_path
                current = target.read_text() if target.exists() else ""
                if current != entry.original_content:
                    d = list(_difflib.unified_diff(
                        entry.original_content.splitlines(keepends=True),
                        current.splitlines(keepends=True),
                        fromfile=f"a/{entry.file_path}",
                        tofile=f"b/{entry.file_path}",
                    ))
                    diff_lines.extend(d)
            if diff_lines:
                analysis_diff = "".join(diff_lines)
        spec_diff = AnalyzeRequestedEvent(
            task_id=task_id, from_agent=AgentName.CONTROLLER, to_agent=AgentName.ANALYZER,
            payload={"project_path": str(self._project_dir), "test_summary": test_summary,
                     "diff": analysis_diff},
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
        temperature_override: float | None = None  # #2 fix

        # ── RepairMode behavioral constraints (Phase2 upgrade) ──
        if self._repair_mode == "REGRESSION_RECOVERY" and len(self._patch_history) > 0:
            # FIX (P0-1): Only roll back when actively regressing (streak >= 2).
            # Previously the fallback at line 463 always triggered because
            # _prev_rollback_entries is set every iteration (line 176), causing
            # every REGRESSION_RECOVERY iteration to undo Builder's work —
            # even when trend was already improving. This created an infinite
            # loop: rollback → Builder improves → rollback again.
            if self._regressing_streak >= 2:
                restored = 0
                source_files = None
                if getattr(self, '_best_snapshot', None):
                    # Use best snapshot: restore actual project file state from best iteration
                    source_files = self._best_snapshot.get("files")
                    self._logger.log(
                        "INFO",
                        f"REGRESSION_RECOVERY: rolling back to best snapshot "
                        f"(iter {self._best_snapshot['iteration']}, "
                        f"pass_rate={self._best_snapshot['test_pass_rate']:.2f})",
                        "controller"
                    )
                if source_files is None and getattr(self, '_prev_rollback_entries', None):
                    # Fallback: restore pre-patch state from rollback entries
                    source_files = {}
                    for entry in self._prev_rollback_entries:
                        source_files[entry.file_path] = entry.original_content
                    self._logger.log(
                        "INFO",
                        "REGRESSION_RECOVERY: rolling back to pre-patch state",
                        "controller"
                    )
                if source_files:
                    restored = self._restore_project_files(source_files)
                    self._logger.log(
                        "INFO",
                        f"REGRESSION_RECOVERY: restored {restored} files",
                        "controller"
                    )
                else:
                    self._logger.log(
                        "WARN",
                        "REGRESSION_RECOVERY: no rollback snapshot available",
                        "controller"
                    )
            else:
                self._logger.log(
                    "INFO",
                    f"REGRESSION_RECOVERY: regressing_streak={self._regressing_streak}, "
                    f"not rolling back — letting Builder try again on current state",
                    "controller"
                )

        if self._repair_mode == "SPEC_COMPLETION":
            # Mark: only allow new file creation, not modification of existing files
            # This is enforced by adding a constraint to the feedback (see below)
            pass

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

            # ── RepairMode: modify payload based on current mode ──
            mode_failures = list(failures)
            mode_feedback = list(feedback)

            if self._repair_mode == "COMPILE_FIX":
                # Only pass compile errors (TEST_ERROR), filter out test failures
                mode_failures = [f for f in failures if f.get("nodeid") == "compile_error"]
                if not mode_failures:
                    mode_failures = list(failures)  # fallback: still pass something
                mode_feedback = [fb for fb in feedback if "[COMPILE_ERROR]" in fb]
                mode_feedback.insert(0, "[MODE:COMPILE_FIX] 只修复编译错误，不要改逻辑，不要跑测试")

            elif self._repair_mode == "SPEC_COMPLETION":
                # Only add new files, don't modify existing ones
                mode_feedback = list(feedback)
                mode_feedback.insert(0, "[MODE:SPEC_COMPLETION] 只新增缺失的文件/功能，不要修改已有代码")

            elif self._repair_mode == "OSCILLATION_BREAK":
                mode_feedback = list(feedback)
                mode_feedback.insert(0, "[MODE:OSCILLATION_BREAK] 前几轮在振荡，请更小步地修改（每次最多3个文件），先解释再动手")
                temperature_override = 0.1  # #2 fix: lower temperature

            elif self._repair_mode == "FINAL_VERIFICATION":
                # N2: tests pass, but need analyzer confirmation.
                # Don't ask Builder to make changes — just re-read DESIGN.md
                # and verify completeness. This is a no-op repair that ensures
                # the analyzer runs on the next iteration.
                mode_feedback = ["[MODE:FINAL_VERIFICATION] 测试已通过，请重新阅读 DESIGN.md 逐项确认所有功能已实现，不做代码修改。如果一切完整，在 ANALYSIS_REPORT.md 中写 ALL CLEAR。"]

            # #3 fix: if last patch was rejected, tell Builder why
            if self._last_patch_rejection is not None:
                last_iter, reason = self._last_patch_rejection
                if last_iter == self._current_iteration - 1:
                    mode_feedback.insert(0, f"[LAST_PATCH_REJECTED] {reason}")
                self._last_patch_rejection = None  # clear after one reminder

            # Build payload with optional temperature override (#2 fix)
            patch_payload: dict = {
                "failures": mode_failures,
                "feedback": mode_feedback,
                "project_path": str(self._project_dir),
                "repair_mode": self._repair_mode,
            }
            if temperature_override is not None:
                patch_payload["temperature_override"] = temperature_override

            patch_request = PatchRequestedEvent(
                task_id=task_id, from_agent=AgentName.CONTROLLER, to_agent=AgentName.BUILDER,
                payload=patch_payload,
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

                # ── Hard patch amplitude enforcement (Phase3 fix) ──
                cfg = self._config.convergence
                allow_large = cfg.allow_large_patch_in_initial and getattr(self, "_current_iteration", 0) <= 1
                hard_reject = getattr(cfg, 'hard_reject_oversized_patch', True)
                if (not allow_large) and hard_reject:
                    if (summary.get("files", 0) > cfg.max_files_per_patch
                            or (summary.get("added", 0) + summary.get("removed", 0)) > cfg.max_lines_per_patch):
                        # Patch too large — reject and roll back
                        reject_evt = PatchFailedEvent(
                            task_id=task_id, from_agent=AgentName.CONTROLLER,
                            to_agent=AgentName.BUILDER,
                            payload={
                                "file_path": "*",
                                "error": (
                                    f"[PATCH_REJECTED] Patch too large: "
                                    f"{summary.get('files', 0)} files, "
                                    f"{summary.get('added', 0) + summary.get('removed', 0)} lines. "
                                    f"Limit: {cfg.max_files_per_patch} files, "
                                    f"{cfg.max_lines_per_patch} lines. "
                                    f"Please make a smaller, focused patch."
                                ),
                                "failed_hunk": None,
                            },
                        )
                        self._event_store.write_event(reject_evt)
                        events.append(reject_evt)
                        # #3 fix: record rejection so next Builder call sees it
                        self._last_patch_rejection = (
                            self._current_iteration,
                            f"[PATCH_REJECTED] Patch too large: "
                            f"{summary.get('files', 0)} files, "
                            f"{summary.get('added', 0) + summary.get('removed', 0)} lines."
                        )
                        # Roll back changes
                        snapshotted_map = {e.file_path: e.original_content for e in self._rollback_entries}
                        for entry in self._rollback_entries:
                            target = self._project_dir / entry.file_path
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_text(entry.original_content)
                        for f in self._project_dir.rglob("*"):
                            if f.is_dir():
                                continue
                            if any(p in str(f) for p in ("__pycache__", ".asr_sandbox", ".git/", ".runtime", ".pytest_cache")):
                                continue
                            rel = str(f.relative_to(self._project_dir))
                            if rel not in snapshotted_map:
                                f.unlink(missing_ok=True)
                        return events  # <-- exit early, Builder will be re-invoked

                applied = PatchAppliedEvent(
                    task_id=task_id, from_agent=AgentName.BUILDER,
                    to_agent=AgentName.CONTROLLER,
                    payload={"file_path": "*", "success": True, "error": None},
                )
                self._event_store.write_event(applied)
                events.append(applied)
                # ── Formal Guards (Phase5): statically enforce invariants ──
                guard_violations = []
                snapshotted_files = {e.file_path for e in self._rollback_entries}

                # Guard 1: No test files deleted
                for entry in self._rollback_entries:
                    if "test_" in entry.file_path or entry.file_path.startswith("tests/"):
                        target = self._project_dir / entry.file_path
                        if not target.exists():
                            guard_violations.append(
                                f"[GUARD:TEST_DELETED] {entry.file_path} — Builder must not delete tests"
                            )

                # Guard 2: Syntax check ALL .py files (modified + new)
                import ast as _ast
                # 2a: check modified files (in _rollback_entries)
                for entry in self._rollback_entries:
                    target = self._project_dir / entry.file_path
                    if target.exists() and entry.file_path.endswith('.py'):
                        try:
                            content = target.read_text()
                            _ast.parse(content)
                        except SyntaxError as se:
                            guard_violations.append(
                                f"[GUARD:SYNTAX_ERROR] {entry.file_path}: {se}"
                            )
                # 2b: P1 fix — check NEW .py files created by Builder
                #     (not in _rollback_entries, so Guard 2a misses them)
                snapshotted_rels = {e.file_path for e in self._rollback_entries}
                for f in self._project_dir.rglob("*.py"):
                    if any(p in str(f) for p in ("__pycache__", ".asr_sandbox", ".runtime", ".pytest_cache", ".git/", ".omo")):
                        continue
                    rel = str(f.relative_to(self._project_dir))
                    if rel in snapshotted_rels:
                        continue  # already checked in 2a
                    try:
                        content = f.read_text()
                        _ast.parse(content)
                    except SyntaxError as se:
                        guard_violations.append(
                            f"[GUARD:SYNTAX_ERROR] {rel}: {se}"
                        )
                    except UnicodeDecodeError:
                        continue

                # Guard 3 (N3): bypass detection — reject patches that bypass tests
                # FIX (Problem D): "pass" as substring matches legit code like
                # "class Foo: pass", "compass", "bypass". Use AST-level detection
                # instead of raw substring matching.
                if summary.get("bypass_detected", False):
                    import ast as _ast_guard
                    for diff_line in diff_text.split("\n"):
                        if not diff_line.startswith("+"):
                            continue
                        stripped = diff_line[1:].strip()
                        # Only check production code lines, not comments/strings
                        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                            continue
                        # Precise patterns:
                        # 1. bare "except:" (no exception type)
                        if stripped.startswith("except:") or stripped.startswith("except :"):
                            guard_violations.append(
                                f"[GUARD:BYPASS] bare except: silences all errors"
                            )
                        # 2. "return expected" hardcoded return
                        if "return expected" in stripped.lower():
                            guard_violations.append(
                                f"[GUARD:BYPASS] hardcoded 'return expected' detected"
                            )
                        # 3. mock( in non-test files — check the diff context
                        # FIX (P2): was checking "test_" not in str(self._project_dir)
                        # which checks the PROJECT DIRECTORY path, not the file path.
                        # If project dir happens to contain "test_" (e.g. /projects/test_asr/),
                        # the guard never triggers. Now check the diff line's file context.
                        if "from unittest.mock import" in stripped:
                            # Find which file this diff hunk belongs to
                            # by looking back for the +++ b/ header
                            diff_lines = diff_text.split("\n")
                            current_file = ""
                            for dl in diff_lines:
                                if dl.startswith("+++ b/"):
                                    current_file = dl[6:]
                                if dl == diff_line:
                                    break
                            if "test_" not in current_file and not current_file.startswith("tests/"):
                                guard_violations.append(
                                    f"[GUARD:BYPASS] unittest.mock imported in production code ({current_file})"
                                )
                        # 4. @pytest.mark.skip
                        if "@pytest.mark.skip" in stripped:
                            guard_violations.append(
                                f"[GUARD:BYPASS] test skipped instead of fixed"
                            )

                if guard_violations:
                    for v in guard_violations:
                        self._logger.log("WARN", v, "controller")
                    reject_evt = PatchFailedEvent(
                        task_id=task_id, from_agent=AgentName.CONTROLLER,
                        to_agent=AgentName.BUILDER,
                        payload={
                            "file_path": "*",
                            "error": f"[PATCH_GUARD_VIOLATION] " + "; ".join(guard_violations[:3]),
                            "failed_hunk": None,
                        },
                    )
                    self._event_store.write_event(reject_evt)
                    events.append(reject_evt)
                    # #3 fix: record rejection so next Builder call sees it
                    self._last_patch_rejection = (
                        self._current_iteration,
                        f"[PATCH_GUARD_VIOLATION] " + "; ".join(guard_violations[:3])
                    )
                    # Roll back
                    for entry in self._rollback_entries:
                        target = self._project_dir / entry.file_path
                        if entry.original_content:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_text(entry.original_content)
                        elif target.exists():
                            target.unlink()
                    for f in self._project_dir.rglob("*"):
                        if f.is_dir():
                            continue
                        if any(p in str(f) for p in ("__pycache__", ".asr_sandbox", ".git/", ".runtime", ".pytest_cache")):
                            continue
                        rel = str(f.relative_to(self._project_dir))
                        if rel not in snapshotted_files:
                            f.unlink(missing_ok=True)
                    return events  # exit early

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
                # ── Patch fingerprint (Phase 2) ──
                if diff_text:
                    fp = self._compute_patch_fingerprint(diff_text)
                    self._patch_fingerprints.append(fp)
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


    # ── Control-Theoretic Metrics (Phase 1) ──

    def _compute_metrics(self, iteration: int,
                          test_events: list, analysis_events: list,
                          repair_events: list,
                          prev_failures: list) -> "ConvergenceMetrics":
        """Compute explicit error signals for this iteration.

        First-principles:
        - test_pass_rate is GROUND TRUTH (tests pass or fail).
          This is the primary signal for trend/oscillation.
        - error_score includes Analyzer findings (another LLM judgment),
          which is noisy. error_score is logged but NOT used for control
          decisions — using a noisy sensor for feedback is a control anti-pattern.
        """
        # ── Hard constraints (GROUND TRUTH) ──
        test_failed_count = _count_failures(test_events)
        test_error_count = sum(1 for e in test_events
                               if e.type in (EventType.TEST_ERROR, EventType.ERROR_OCCURRED))

        # ── test_pass_rate: ground truth, PRIMARY control signal ──
        # FIX (Problem B): use max() for both total and passed to avoid
        # double-counting when multiple test events exist in one round.
        # Each test run produces exactly one TestFailed/Passed/Error event
        # with the full {total, passed, failed} snapshot. Taking max()
        # picks the most recent (and most accurate) snapshot.
        total_tests = 0
        passed_tests = 0
        for evt in test_events:
            if hasattr(evt, 'payload'):
                total_tests = max(total_tests, evt.payload.get("total", 0))
                passed_tests = max(passed_tests, evt.payload.get("passed", 0))
        test_pass_rate = passed_tests / total_tests if total_tests > 0 else 0.0

        # ── Semantic signals (noisy — from Analyzer LLM) ──
        missing_feature_count = 0
        logic_issue_count = 0
        constraint_violation_count = 0
        high_severity_count = 0

        for evt in analysis_events:
            if evt.type == EventType.SPEC_DIFF_FOUND:
                missing_feature_count += len(evt.payload.get("missing_features", []))
                logic_issue_count += len(evt.payload.get("logic_issues", []))
                constraint_violation_count += len(evt.payload.get("constraint_violations", []))
            elif evt.type == EventType.ANALYZER_FEEDBACK:
                high_severity_count += evt.payload.get("high_severity_count", 0)

        # ── Patch signals ──
        patch_count = sum(1 for e in repair_events if e.type == EventType.PATCH_GENERATED)
        changed_file_count = 0
        changed_line_count = 0
        for e in repair_events:
            if e.type == EventType.PATCH_APPLIED:
                summary = e.payload.get("summary", {})
                if isinstance(summary, dict):
                    changed_file_count += summary.get("files", 0)
                    changed_line_count += summary.get("added", 0) + summary.get("removed", 0)

        # ── Stability signals ──
        rollback_count = sum(1 for e in repair_events if e.type == EventType.PATCH_ROLLED_BACK)

        # N1: compute failure fingerprint and repeated_failure_count
        current_fp = self._compute_failure_fingerprint(prev_failures)
        self._failure_fingerprints.append(current_fp)
        repeated_failure_count = 0
        if len(self._failure_fingerprints) >= 2 and current_fp != "none":
            # Count how many of the last 3 rounds had the same fingerprint
            recent = self._failure_fingerprints[-4:-1]  # exclude current
            repeated_failure_count = sum(1 for fp in recent if fp == current_fp)

        # ── Oscillation score ──
        # Primary: test_pass_rate history (does it go up-down-up?)
        oscillation_score = 0.0
        if len(self._pass_rate_history) >= 4:
            recent = self._pass_rate_history[-4:]
            deltas = [recent[i] - recent[i-1] for i in range(1, len(recent))]
            # Alternating +/- deltas = oscillation
            if len(deltas) >= 2 and deltas[-1] * deltas[-2] < 0:
                oscillation_score = 0.7
            if len(deltas) >= 3 and deltas[-1] * deltas[-2] < 0 and deltas[-2] * deltas[-3] < 0:
                oscillation_score = 1.0
        # Secondary: patch fingerprint (catches exact repetition)
        if len(self._patch_fingerprints) >= 4:
            recent_fp = self._patch_fingerprints[-4:]
            if len(set(recent_fp)) <= 2 and recent_fp[0] == recent_fp[2] and recent_fp[1] == recent_fp[3]:
                oscillation_score = max(oscillation_score, 0.9)
        # N1: failure fingerprint — same tests failing 3+ times = stuck loop
        if repeated_failure_count >= 3:
            oscillation_score = max(oscillation_score, 0.85)

        # ── Error score (noisy — includes Analyzer judgment) ──
        # Weight justification (first-principles):
        #   w_test_error=2.0  — compile/syntax error is more fundamental than
        #                         a test failure (Builder can't write valid code)
        #   w_test_failed=1.0  — baseline: one test failure = 1 unit
        #   w_missing_feature=1.5 — missing feature > wrong impl (nothing vs. something)
        #   w_high_severity=2.0 — Analyzer marked this as critical
        #   w_patch_regression=1.0 — a patch that made things worse
        cfg = self._config.convergence
        error_score = (
            cfg.w_test_failed * test_failed_count
            + cfg.w_test_error * test_error_count
            + cfg.w_missing_feature * missing_feature_count
            + cfg.w_logic_issue * logic_issue_count
            + cfg.w_constraint_violation * constraint_violation_count
            + cfg.w_high_severity * high_severity_count
            + cfg.w_patch_regression * rollback_count
        )

        # ── Trend: based on test_pass_rate (ground truth), NOT error_score ──
        trend = "unknown"
        if len(self._pass_rate_history) >= 2:
            prev_rate = self._pass_rate_history[-1]
            delta = test_pass_rate - prev_rate
            if delta > 0.05:
                trend = "improving"
            elif delta < -0.05:
                trend = "regressing"
            else:
                trend = "stalled"
                # Check for oscillation pattern in pass rate history
                if len(self._pass_rate_history) >= 4:
                    r = self._pass_rate_history[-4:]
                    if (r[0] < r[1] > r[2] < r[3]) or (r[0] > r[1] < r[2] > r[3]):
                        trend = "oscillating"

        metrics = ConvergenceMetrics(
            iteration=iteration,
            test_failed_count=test_failed_count,
            test_error_count=test_error_count,
            missing_feature_count=missing_feature_count,
            logic_issue_count=logic_issue_count,
            constraint_violation_count=constraint_violation_count,
            high_severity_count=high_severity_count,
            patch_count=patch_count,
            changed_file_count=changed_file_count,
            changed_line_count=changed_line_count,
            rollback_count=rollback_count,
            repeated_failure_count=repeated_failure_count,
            oscillation_score=oscillation_score,
            test_pass_rate=test_pass_rate,
            error_score=error_score,
            trend=trend,
        )

        self._metrics_history.append(metrics)
        self._error_score_history.append(error_score)
        self._pass_rate_history.append(test_pass_rate)
        # P0 fix: save best snapshot with ACTUAL project file state (post-Builder),
        # not _rollback_entries (which are pre-Builder snapshots and get cleared).
        # When test_pass_rate hits a new high, snapshot all .py files so
        # REGRESSION_RECOVERY can restore the best-known-good state.
        if not hasattr(self, '_best_snapshot') or self._best_snapshot is None:
            self._best_snapshot = {
                "iteration": iteration,
                "test_pass_rate": test_pass_rate,
                "files": self._snapshot_project_files(),
            }
        elif test_pass_rate > self._best_snapshot["test_pass_rate"] + 0.01:
            self._best_snapshot = {
                "iteration": iteration,
                "test_pass_rate": test_pass_rate,
                "files": self._snapshot_project_files(),
            }
            self._logger.log(
                "INFO",
                f"Best snapshot saved: iter={iteration}, pass_rate={test_pass_rate:.2f}",
                "controller"
            )

        return metrics

    def _emit_metrics(self, task_id: str, metrics: "ConvergenceMetrics",
                      result: "ConvergenceResult") -> None:
        """Emit ConvergenceMetricsEvent and update progress callback."""
        evt = ConvergenceMetricsEvent(
            task_id=task_id,
            from_agent=AgentName.CONTROLLER,
            to_agent=AgentName.SYSTEM,
            payload={
                "metrics": metrics.model_dump(),
                "trend": metrics.trend,
                "error_score": metrics.error_score,
                "previous_error_score": self._error_score_history[-2] if len(self._error_score_history) >= 2 else None,
            },
        )
        self._write_and_log(evt, result)

        # Log convergence trend
        if self._logger:
            self._logger.log_convergence(
                self._current_iteration, metrics.test_failed_count,
                "METRICS",
                f"pass_rate={metrics.test_pass_rate:.2f} trend={metrics.trend} "
                f"[Analyzer噪声]error_score={metrics.error_score:.1f}"
            )

    def _compute_patch_fingerprint(self, diff_text: str) -> str:
        """Compute SHA-256 fingerprint of a patch diff."""
        import hashlib
        return hashlib.sha256(diff_text.encode("utf-8")).hexdigest()[:16]

    def _compute_failure_fingerprint(self, failures: list[dict]) -> str:
        """N1: Compute SHA-256 fingerprint of test failure signatures.

        Groups failures by nodeid (ignoring variable error messages) so that
        the same test failing across iterations produces the same fingerprint.
        """
        import hashlib
        if not failures:
            return "none"
        nodeids = sorted(f.get("nodeid", "?") for f in failures)
        raw = "|".join(nodeids)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _snapshot_project_files(self) -> dict[str, str]:
        """Snapshot all project source files (post-Builder state).

        P0 fix: _rollback_entries stores PRE-Builder state and gets cleared
        in run(). For REGRESSION_RECOVERY we need the POST-Builder state at
        the best iteration. This method captures the actual file contents.
        """
        skip = ("__pycache__", ".asr_sandbox", ".git/", ".runtime", ".pytest_cache", ".omo")
        result = {}
        for f in self._project_dir.rglob("*"):
            if f.is_dir():
                continue
            if any(p in str(f) for p in skip):
                continue
            try:
                content = f.read_text()
                rel = str(f.relative_to(self._project_dir))
                result[rel] = content
            except (UnicodeDecodeError, OSError):
                continue
        return result

    def _restore_project_files(self, files: dict[str, str]) -> int:
        """Restore project files from a snapshot dict. Returns count restored."""
        skip = ("__pycache__", ".asr_sandbox", ".git/", ".runtime", ".pytest_cache", ".omo")
        restored = 0
        # Restore all files from snapshot
        for rel, content in files.items():
            target = self._project_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.write_text(content)
                restored += 1
            except OSError:
                pass
        # Remove files that exist now but weren't in snapshot (created after best)
        snapshotted_set = set(files.keys())
        for f in self._project_dir.rglob("*"):
            if f.is_dir():
                continue
            if any(p in str(f) for p in skip):
                continue
            rel = str(f.relative_to(self._project_dir))
            if rel not in snapshotted_set:
                f.unlink(missing_ok=True)
        return restored


    def _check_and_switch_mode(self, metrics: "ConvergenceMetrics",
                                task_id: str, result: "ConvergenceResult") -> str:
        """Decide whether to switch RepairMode, with hysteresis to prevent flapping."""
        # #6 fix: update trend history and streaks for hysteresis
        self._trend_history.append(metrics.trend)
        if len(self._trend_history) > 5:
            self._trend_history = self._trend_history[-5:]

        # Update streaks
        if metrics.trend == "stalled":
            self._stalled_streak += 1
        else:
            self._stalled_streak = 0
        if metrics.trend == "regressing":
            self._regressing_streak += 1
        else:
            self._regressing_streak = 0
        if metrics.trend == "improving":
            self._improving_streak += 1
        else:
            self._improving_streak = 0

        # Decide new mode (hysteresis: only switch if streak >= 2)
        new_mode = self._repair_mode  # default: keep current

        # P3 fix: exit OSCILLATION_BREAK when improving for 2+ iters
        if self._repair_mode == "OSCILLATION_BREAK" and self._improving_streak >= 2:
            new_mode = "TEST_FIX"
            self._logger.log(
                "INFO",
                f"RepairMode: OSCILLATION_BREAK → TEST_FIX "
                f"(improving_streak={self._improving_streak}, oscillation resolved)",
                "controller"
            )

        # FIX (P0-1): exit REGRESSION_RECOVERY as soon as trend improves once.
        # No need to wait for streak >= 2 — the rollback already happened once,
        # and if Builder made progress on the rolled-back state, we should let
        # it continue without further rollback interference.
        elif self._repair_mode == "REGRESSION_RECOVERY" and self._improving_streak >= 1:
            new_mode = "TEST_FIX"
            self._logger.log(
                "INFO",
                f"RepairMode: REGRESSION_RECOVERY → TEST_FIX "
                f"(improving_streak={self._improving_streak}, regression recovered)",
                "controller"
            )

        # FIX (P0-2): exit FINAL_VERIFICATION if Analyzer aligned (safety net —
        # the primary exit is in run() where we have analysis_events context).
        # If _check_and_switch_mode is called while still in FINAL_VERIFICATION
        # and spec_aligned was true, fall through to TEST_FIX.
        elif self._repair_mode == "FINAL_VERIFICATION" and metrics.test_pass_rate >= 1.0:
            # Tests all pass and we're in FINAL_VERIFICATION — if Analyzer
            # didn't flag anything this round, let convergence logic handle it.
            # If Analyzer DID flag something, run() already switched the mode.
            pass  # no-op: let convergence_streak logic handle it

        elif metrics.oscillation_score >= 0.7:
            new_mode = "OSCILLATION_BREAK"
            self._write_and_log(StuckEvent(
                task_id=task_id, from_agent=AgentName.CONTROLLER,
                to_agent=AgentName.SYSTEM,
                payload={"reason": "pass_rate_oscillation",
                         "last_iteration": metrics.iteration,
                         "oscillation_score": metrics.oscillation_score},
            ), result)

        elif self._regressing_streak >= 2 and metrics.iteration > 3:
            new_mode = "REGRESSION_RECOVERY"

        elif self._stalled_streak >= 2 and metrics.iteration > 2:
            if metrics.missing_feature_count > 0:
                new_mode = "SPEC_COMPLETION"
            else:
                new_mode = "TEST_FIX"

        elif metrics.iteration == 1:
            new_mode = "INITIAL_GENERATION"

        # Apply mode change
        if new_mode != self._repair_mode:
            self._logger.log(
                "INFO",
                f"RepairMode: {self._repair_mode} → {new_mode} "
                f"(trend={metrics.trend}, pass_rate={metrics.test_pass_rate:.2f}, "
                f"stalled_streak={self._stalled_streak})",
                "controller"
            )
            if not hasattr(self, '_mode_history'):
                self._mode_history = []
            self._mode_history.append((new_mode, metrics.iteration))
            self._repair_mode = new_mode

        return self._repair_mode


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
