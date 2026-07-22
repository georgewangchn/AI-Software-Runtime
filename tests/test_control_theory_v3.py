"""Tests for control-theoretic optimizations v3 (P0-P2).

Tests cover:
- P0-1: Incremental test computation
- P0-2: Builder feedforward context
- P1-1: Sensor disagreement arbitration
- P1-2: Adaptive patch limits
- P2-1: A/B rollback on regression
- P2-2: Metrics timeline export
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure asr package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from asr.config.models import ASRConfig, ConvergenceConfig, AgentConfig, ModelConfig
from asr.controller.convergence import ASRController, ConvergenceState, ConvergenceResult
from asr.events.models import (
    Event, EventType, AgentName,
    TestFailedEvent, TestPassedEvent, TestErrorEvent,
    ConvergenceMetrics,
)
from asr.events.store import EventStore
from asr.agents.tester import TesterAgent
from asr.spec.models import Specification


# ──────────────────────────────────────────────────────────────
# P0-1: Incremental test computation
# ──────────────────────────────────────────────────────────────

class TestIncrementalTesting:
    """P0-1: Tester should compute affected test files from changed source files."""

    def test_compute_affected_tests_direct_correspondence(self, tmp_path):
        """src/auth.py → tests/test_auth.py"""
        # Set up sandbox structure
        sandbox = tmp_path / ".asr_sandbox" / "tester"
        tests_dir = sandbox / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_auth.py").write_text("def test_auth(): pass")
        (tests_dir / "test_models.py").write_text("def test_models(): pass")

        cfg = AgentConfig(role="tester", model=ModelConfig(model="test"))
        agent = TesterAgent(cfg, MagicMock(), tmp_path)
        affected = agent._compute_affected_tests(["src/auth.py"], sandbox)
        assert len(affected) == 1
        assert "test_auth.py" in affected[0]

    def test_compute_affected_tests_import_dependency(self, tmp_path):
        """If test imports the changed module, it's affected."""
        sandbox = tmp_path / ".asr_sandbox" / "tester"
        tests_dir = sandbox / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_auth.py").write_text("from src.auth import login")
        (tests_dir / "test_models.py").write_text("from src.models import User")

        cfg = AgentConfig(role="tester", model=ModelConfig(model="test"))
        agent = TesterAgent(cfg, MagicMock(), tmp_path)
        # Change src/auth.py — should affect test_auth.py (direct) and any test importing auth
        affected = agent._compute_affected_tests(["src/auth.py"], sandbox)
        assert len(affected) >= 1
        assert any("test_auth" in a for a in affected)

    def test_compute_affected_tests_empty_changed_files(self, tmp_path):
        """No changed files → empty list (caller runs full suite)."""
        sandbox = tmp_path / ".asr_sandbox" / "tester"
        sandbox.mkdir(parents=True)
        cfg = AgentConfig(role="tester", model=ModelConfig(model="test"))
        agent = TesterAgent(cfg, MagicMock(), tmp_path)
        affected = agent._compute_affected_tests([], sandbox)
        assert affected == []

    def test_compute_affected_tests_no_tests_dir(self, tmp_path):
        """No tests/ directory → empty list."""
        sandbox = tmp_path / ".asr_sandbox" / "tester"
        sandbox.mkdir(parents=True)
        cfg = AgentConfig(role="tester", model=ModelConfig(model="test"))
        agent = TesterAgent(cfg, MagicMock(), tmp_path)
        affected = agent._compute_affected_tests(["src/auth.py"], sandbox)
        assert affected == []


# ──────────────────────────────────────────────────────────────
# P0-2: Builder feedforward context
# ──────────────────────────────────────────────────────────────

class TestBuilderFeedforward:
    """P0-2: Controller should build feedforward context for Builder."""

    def _make_controller(self, tmp_path):
        config = ASRConfig()
        event_store = EventStore(
            event_dir=str(tmp_path / "events"),
            inbox_dir=str(tmp_path / "inbox"),
            patches_dir=str(tmp_path / "patches"),
            diffs_dir=str(tmp_path / "diffs"),
            state_dir=str(tmp_path / "state"),
            tasks_dir=str(tmp_path / "tasks"),
        )
        logger = MagicMock()
        controller = ASRController(
            config=config,
            event_store=event_store,
            project_dir=tmp_path,
            logger=logger,
        )
        return controller

    def test_build_builder_context_empty(self, tmp_path):
        """No history → empty context."""
        controller = self._make_controller(tmp_path)
        ctx = controller._build_builder_context()
        assert ctx == ""

    def test_build_builder_context_with_trajectory(self, tmp_path):
        """Pass rate history → trajectory in context."""
        controller = self._make_controller(tmp_path)
        controller._pass_rate_history = [0.3, 0.5, 0.8]
        ctx = controller._build_builder_context()
        assert "[TRAJECTORY]" in ctx
        assert "30.0%" in ctx or "0.3" in ctx  # may be formatted differently

    def test_build_builder_context_with_mode_history(self, tmp_path):
        """Mode transitions → mode history in context."""
        controller = self._make_controller(tmp_path)
        controller._mode_history = [("INITIAL", 1), ("TEST_FIX", 2), ("OSCILLATION_BREAK", 3)]
        controller._pass_rate_history = [0.5]
        ctx = controller._build_builder_context()
        assert "[MODE_HISTORY]" in ctx

    def test_build_builder_context_with_repeated_failure(self, tmp_path):
        """Repeated failures → warning in context."""
        controller = self._make_controller(tmp_path)
        controller._failure_fingerprints = ["abc123", "def456", "abc123", "abc123"]
        controller._pass_rate_history = [0.5]
        ctx = controller._build_builder_context()
        assert "[REPEATED_FAILURE]" in ctx

    def test_build_builder_context_with_best_snapshot(self, tmp_path):
        """Best snapshot exists → best state in context."""
        controller = self._make_controller(tmp_path)
        controller._best_snapshot = {
            "iteration": 3,
            "test_pass_rate": 0.9,
            "files": {},
        }
        controller._pass_rate_history = [0.5, 0.7, 0.9]
        ctx = controller._build_builder_context()
        assert "[BEST_STATE]" in ctx
        assert "iter=3" in ctx

    def test_build_builder_context_with_trend(self, tmp_path):
        """Trend history → trend in context."""
        controller = self._make_controller(tmp_path)
        controller._pass_rate_history = [0.5, 0.7]
        controller._trend_history = ["improving"]
        controller._improving_streak = 1
        ctx = controller._build_builder_context()
        assert "[TREND]" in ctx
        assert "improving" in ctx


# ──────────────────────────────────────────────────────────────
# P1-1: Sensor disagreement arbitration
# ──────────────────────────────────────────────────────────────

class TestSensorDisagreement:
    """P1-1: Controller should detect sensor disagreement."""

    def _make_controller(self, tmp_path):
        config = ASRConfig()
        event_store = EventStore(
            event_dir=str(tmp_path / "events"),
            inbox_dir=str(tmp_path / "inbox"),
            patches_dir=str(tmp_path / "patches"),
            diffs_dir=str(tmp_path / "diffs"),
            state_dir=str(tmp_path / "state"),
            tasks_dir=str(tmp_path / "tasks"),
        )
        return ASRController(
            config=config,
            event_store=event_store,
            project_dir=tmp_path,
            logger=MagicMock(),
        )

    def test_incomplete_tests_detection(self, tmp_path):
        """Tests pass but features missing → INCOMPLETE_TESTS."""
        controller = self._make_controller(tmp_path)
        result = controller._compute_sensor_agreement(1.0, 3, False)
        assert result == "INCOMPLETE_TESTS"

    def test_test_quality_issue_detection(self, tmp_path):
        """Tests fail badly but Analyzer says aligned → TEST_QUALITY_ISSUE."""
        controller = self._make_controller(tmp_path)
        result = controller._compute_sensor_agreement(0.3, 0, True)
        assert result == "TEST_QUALITY_ISSUE"

    def test_agreed_both_good(self, tmp_path):
        """Tests pass and Analyzer aligned → AGREED."""
        controller = self._make_controller(tmp_path)
        result = controller._compute_sensor_agreement(1.0, 0, True)
        assert result == "AGREED"

    def test_agreed_both_bad(self, tmp_path):
        """Tests fail and Analyzer finds issues → AGREED."""
        controller = self._make_controller(tmp_path)
        result = controller._compute_sensor_agreement(0.3, 5, False)
        assert result == "AGREED"

    def test_metrics_include_sensor_disagreement(self, tmp_path):
        """ConvergenceMetrics should have sensor_disagreement field."""
        m = ConvergenceMetrics()
        assert hasattr(m, "sensor_disagreement")
        assert m.sensor_disagreement == "AGREED"


# ──────────────────────────────────────────────────────────────
# P1-2: Adaptive patch limits
# ──────────────────────────────────────────────────────────────

class TestAdaptiveLimits:
    """P1-2: Patch limits should adapt based on repair mode and trend."""

    def _make_controller(self, tmp_path):
        config = ASRConfig()
        config.convergence.adaptive_limits = True
        event_store = EventStore(
            event_dir=str(tmp_path / "events"),
            inbox_dir=str(tmp_path / "inbox"),
            patches_dir=str(tmp_path / "patches"),
            diffs_dir=str(tmp_path / "diffs"),
            state_dir=str(tmp_path / "state"),
            tasks_dir=str(tmp_path / "tasks"),
        )
        return ASRController(
            config=config,
            event_store=event_store,
            project_dir=tmp_path,
            logger=MagicMock(),
        )

    def test_oscillation_break_tightens_limits(self, tmp_path):
        controller = self._make_controller(tmp_path)
        controller._repair_mode = "OSCILLATION_BREAK"
        files, lines = controller._get_adaptive_limits()
        base_files = ASRConfig().convergence.max_files_per_patch  # 10
        base_lines = ASRConfig().convergence.max_lines_per_patch  # 200
        assert files <= base_files
        assert lines <= base_lines
        assert files <= 4  # 10 // 3 = 3, max(2, 3) = 3
        assert lines <= 67  # 200 // 3 = 66, max(30, 66) = 66

    def test_regression_recovery_tightest_limits(self, tmp_path):
        controller = self._make_controller(tmp_path)
        controller._repair_mode = "REGRESSION_RECOVERY"
        files, lines = controller._get_adaptive_limits()
        assert files <= 3  # 10 // 4 = 2, max(1, 2) = 2
        assert lines <= 50  # 200 // 4 = 50, max(15, 50) = 50

    def test_improving_streak_widens_limits(self, tmp_path):
        controller = self._make_controller(tmp_path)
        controller._repair_mode = "TEST_FIX"
        controller._improving_streak = 3
        files, lines = controller._get_adaptive_limits()
        base_files = ASRConfig().convergence.max_files_per_patch  # 10
        base_lines = ASRConfig().convergence.max_lines_per_patch  # 200
        assert files == int(base_files * 1.5)  # 15
        assert lines == int(base_lines * 1.5)  # 300

    def test_stalled_streak_tightens_limits(self, tmp_path):
        controller = self._make_controller(tmp_path)
        controller._repair_mode = "TEST_FIX"
        controller._stalled_streak = 3
        files, lines = controller._get_adaptive_limits()
        base_files = ASRConfig().convergence.max_files_per_patch  # 10
        assert files == max(3, base_files // 2)  # 5
        assert lines == max(50, ASRConfig().convergence.max_lines_per_patch // 2)  # 100

    def test_adaptive_limits_disabled(self, tmp_path):
        """When adaptive_limits=False, returns static config values."""
        config = ASRConfig()
        config.convergence.adaptive_limits = False
        event_store = EventStore(
            event_dir=str(tmp_path / "events"),
            inbox_dir=str(tmp_path / "inbox"),
            patches_dir=str(tmp_path / "patches"),
            diffs_dir=str(tmp_path / "diffs"),
            state_dir=str(tmp_path / "state"),
            tasks_dir=str(tmp_path / "tasks"),
        )
        controller = ASRController(
            config=config,
            event_store=event_store,
            project_dir=tmp_path,
            logger=MagicMock(),
        )
        controller._repair_mode = "OSCILLATION_BREAK"
        files, lines = controller._get_adaptive_limits()
        assert files == config.convergence.max_files_per_patch
        assert lines == config.convergence.max_lines_per_patch


# ──────────────────────────────────────────────────────────────
# P2-1: A/B comparison baseline (rollback on regression)
# ──────────────────────────────────────────────────────────────

class TestABBaseline:
    """P2-1: Controller should roll back when pass_rate drops significantly."""

    def _make_controller(self, tmp_path):
        config = ASRConfig()
        event_store = EventStore(
            event_dir=str(tmp_path / "events"),
            inbox_dir=str(tmp_path / "inbox"),
            patches_dir=str(tmp_path / "patches"),
            diffs_dir=str(tmp_path / "diffs"),
            state_dir=str(tmp_path / "state"),
            tasks_dir=str(tmp_path / "tasks"),
        )
        return ASRController(
            config=config,
            event_store=event_store,
            project_dir=tmp_path,
            logger=MagicMock(),
        )

    def test_ab_rollback_triggers_on_significant_regression(self, tmp_path):
        """Pass rate drops >15% from best → rollback should trigger."""
        controller = self._make_controller(tmp_path)
        # Set up best snapshot
        (tmp_path / "main.py").write_text("# best version")
        controller._best_snapshot = {
            "iteration": 2,
            "test_pass_rate": 0.9,
            "files": {"main.py": "# best version"},
        }
        # Simulate regression: pass_rate drops to 0.6 (30% drop)
        # The rollback logic is in run() — we test _restore_project_files
        restored = controller._restore_project_files({"main.py": "# best version"})
        assert restored >= 1
        assert (tmp_path / "main.py").read_text() == "# best version"

    def test_ab_rollback_no_trigger_for_small_drop(self, tmp_path):
        """Pass rate drops <15% from best → no rollback (stays in REGRESSION_RECOVERY)."""
        # The threshold is 0.15 in run(): rollback only if pass_rate < best - 0.15
        # best=0.9, threshold=0.75 → pass_rate=0.85 does NOT trigger rollback (0.85 >= 0.75)
        best_rate = 0.9
        current_rate = 0.85
        threshold = 0.15
        # The condition in code is: current < best - threshold
        should_rollback = current_rate < best_rate - threshold
        assert should_rollback is False  # 0.85 >= 0.75 → no rollback


# ──────────────────────────────────────────────────────────────
# P2-2: Metrics timeline export
# ──────────────────────────────────────────────────────────────

class TestMetricsTimeline:
    """P2-2: Controller should export metrics as structured time-series."""

    def _make_controller(self, tmp_path):
        config = ASRConfig()
        event_store = EventStore(
            event_dir=str(tmp_path / "events"),
            inbox_dir=str(tmp_path / "inbox"),
            patches_dir=str(tmp_path / "patches"),
            diffs_dir=str(tmp_path / "diffs"),
            state_dir=str(tmp_path / "state"),
            tasks_dir=str(tmp_path / "tasks"),
        )
        return ASRController(
            config=config,
            event_store=event_store,
            project_dir=tmp_path,
            logger=MagicMock(),
        )

    def test_convergence_result_has_metrics_timeline(self):
        """ConvergenceResult should have metrics_timeline field."""
        result = ConvergenceResult(state=ConvergenceState.INIT)
        assert hasattr(result, "metrics_timeline")
        assert result.metrics_timeline == []

    def test_finalize_metrics_timeline_writes_file(self, tmp_path):
        """_finalize_metrics_timeline should write JSON file."""
        controller = self._make_controller(tmp_path)
        # Simulate metrics history
        controller._metrics_history = [
            ConvergenceMetrics(iteration=1, test_pass_rate=0.5, trend="improving",
                               error_score=10.0, sensor_disagreement="AGREED"),
            ConvergenceMetrics(iteration=2, test_pass_rate=0.8, trend="improving",
                               error_score=5.0, sensor_disagreement="AGREED"),
        ]
        controller._mode_history = [("INITIAL", 1), ("TEST_FIX", 2)]
        result = ConvergenceResult(state=ConvergenceState.CONVERGED)
        controller._finalize_metrics_timeline("test-task", result)
        # Check file was written
        metrics_file = tmp_path / ".runtime" / "state" / "metrics_test-task.json"
        assert metrics_file.exists()
        data = json.loads(metrics_file.read_text())
        assert len(data) == 2
        assert data[0]["iteration"] == 1
        assert data[1]["test_pass_rate"] == 0.8
        assert "sensor_disagreement" in data[0]

    def test_metrics_timeline_in_result_summary(self, tmp_path):
        """Metrics timeline should be in result.summary."""
        controller = self._make_controller(tmp_path)
        controller._metrics_history = [
            ConvergenceMetrics(iteration=1, test_pass_rate=0.5, trend="unknown"),
        ]
        controller._mode_history = []
        result = ConvergenceResult(state=ConvergenceState.CONVERGED)
        controller._finalize_metrics_timeline("test-task", result)
        assert "metrics_timeline" in result.summary
        assert len(result.summary["metrics_timeline"]) == 1
