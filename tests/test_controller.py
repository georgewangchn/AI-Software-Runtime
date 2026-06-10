"""Tests for ASR controller convergence module."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from asr.controller.convergence import (
    ASRController, ConvergenceState, ConvergenceResult,
    _count_failures, _EXPECTED_TYPES
)
from asr.config.models import ASRConfig, ConvergenceConfig
from asr.events.models import (
    EventType, AgentName,
    TaskCreatedEvent, TestStartedEvent, TestFailedEvent, TestPassedEvent,
    TestErrorEvent, SpecDiffFoundEvent, SpecAlignedEvent, PatchGeneratedEvent,
    PatchAppliedEvent, ConvergedEvent, StuckEvent, ConvergenceIterationEvent
)
from asr.events.store import EventStore
from asr.spec.models import Specification
from asr.agents.base import BaseAgent
from asr.logger import ASRLogger


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        (project_dir / "main.py").write_text("print('hello')")
        (project_dir / "utils.py").write_text("def foo(): return 42")
        yield project_dir


@pytest.fixture
def event_store():
    """Create an EventStore instance."""
    return EventStore()


@pytest.fixture
def minimal_config():
    """Create minimal ASR config."""
    return ASRConfig(convergence=ConvergenceConfig(max_iterations=3))


class TestConvergenceState:
    """Tests for ConvergenceState enum."""

    def test_convergence_state_values(self):
        """Test ConvergenceState enum values."""
        assert ConvergenceState.INIT == "init"
        assert ConvergenceState.GENERATING == "generating"
        assert ConvergenceState.TESTING == "testing"
        assert ConvergenceState.ANALYZING == "analyzing"
        assert ConvergenceState.REPAIRING == "repairing"
        assert ConvergenceState.CONVERGED == "converged"
        assert ConvergenceState.STUCK == "stuck"


class TestConvergenceResult:
    """Tests for ConvergenceResult dataclass."""

    def test_convergence_result_defaults(self):
        """Test ConvergenceResult with default values."""
        result = ConvergenceResult(state=ConvergenceState.INIT)
        assert result.state == ConvergenceState.INIT
        assert result.iterations == 0
        assert result.events == []
        assert result.summary == {}

    def test_convergence_result_with_data(self):
        """Test ConvergenceResult with all fields."""
        events = [TaskCreatedEvent(
            task_id="task-1", from_agent=AgentName.CONTROLLER, to_agent=AgentName.BUILDER
        )]
        summary = {"dag": {"total_nodes": 5}}

        result = ConvergenceResult(
            state=ConvergenceState.CONVERGED,
            iterations=5,
            events=events,
            summary=summary
        )
        assert result.state == ConvergenceState.CONVERGED
        assert result.iterations == 5
        assert len(result.events) == 1
        assert result.summary == summary


class TestASRController:
    """Tests for ASRController class."""

    def test_controller_initialization(self, minimal_config, event_store, temp_project_dir):
        """Test ASRController initialization."""
        controller = ASRController(
            config=minimal_config,
            event_store=event_store,
            project_dir=temp_project_dir
        )
        assert controller._config == minimal_config
        assert controller._event_store == event_store
        assert controller._project_dir == temp_project_dir
        assert controller._builder is None
        assert controller._tester is None
        assert controller._analyzer is None
        assert controller._use_decoupled is False
        assert len(controller._patch_history) == 0

    def test_controller_with_logger(self, minimal_config, event_store, temp_project_dir):
        """Test ASRController with logger."""
        logger = ASRLogger()
        controller = ASRController(
            config=minimal_config,
            event_store=event_store,
            project_dir=temp_project_dir,
            logger=logger
        )
        assert controller._logger == logger

    def test_controller_with_decoupled_mode(self, minimal_config, event_store, temp_project_dir):
        """Test ASRController with decoupled mode."""
        controller = ASRController(
            config=minimal_config,
            event_store=event_store,
            project_dir=temp_project_dir,
            use_decoupled_a2a=True
        )
        assert controller._use_decoupled is True

    def test_controller_with_agents(self, minimal_config, event_store, temp_project_dir):
        """Test ASRController with agents."""
        class MockAgent(BaseAgent):
            def __init__(self, name, event_store):
                super().__init__(name=name, event_store=event_store)
            async def process(self, event):
                return []

        builder = MockAgent(AgentName.BUILDER, event_store)
        tester = MockAgent(AgentName.TESTER, event_store)
        analyzer = MockAgent(AgentName.ANALYZER, event_store)

        controller = ASRController(
            config=minimal_config,
            event_store=event_store,
            project_dir=temp_project_dir,
            builder=builder,
            tester=tester,
            analyzer=analyzer
        )
        assert controller._builder is not None
        assert controller._tester is not None
        assert controller._analyzer is not None

    def test_controller_extract_test_summary(self, minimal_config, event_store, temp_project_dir):
        """Test _extract_test_summary method."""
        controller = ASRController(
            config=minimal_config,
            event_store=event_store,
            project_dir=temp_project_dir
        )

        events = [
            TestPassedEvent(
                task_id="task-1", from_agent=AgentName.TESTER, to_agent=AgentName.CONTROLLER,
                payload={"total": 10, "passed": 8}
            ),
            TestFailedEvent(
                task_id="task-1", from_agent=AgentName.TESTER, to_agent=AgentName.CONTROLLER,
                payload={"total": 10, "failed": 2, "failures": [{"nodeid": "test_1", "message": "error"}]}
            )
        ]

        summary = controller._extract_test_summary(events)
        assert summary["total"] == 10
        assert summary["passed"] == 8
        assert summary["failed"] == 2
        assert len(summary["failures"]) == 1

    def test_controller_resolve_target(self, minimal_config, event_store, temp_project_dir):
        """Test _resolve_target method."""
        controller = ASRController(
            config=minimal_config,
            event_store=event_store,
            project_dir=temp_project_dir
        )

        assert controller._resolve_target("main.py") == temp_project_dir / "main.py"
        assert controller._resolve_target("test_main.py") is None
        assert controller._resolve_target("") is None

    def test_controller_read_file_safe(self, minimal_config, event_store, temp_project_dir):
        """Test _read_file_safe method."""
        controller = ASRController(
            config=minimal_config,
            event_store=event_store,
            project_dir=temp_project_dir
        )

        content = controller._read_file_safe("main.py")
        assert content == "print('hello')"

        content = controller._read_file_safe("nonexistent.py")
        assert content is None

    def test_controller_compute_risk(self, minimal_config, event_store, temp_project_dir):
        """Test _compute_risk method."""
        controller = ASRController(
            config=minimal_config,
            event_store=event_store,
            project_dir=temp_project_dir
        )

        diff = "--- a/test.py\n+++ b/test.py\n-old\n+new\n-old2\n+new2"
        risk = controller._compute_risk(diff)
        assert "score" in risk
        assert "lines_added" in risk
        assert "lines_removed" in risk
        assert "files_touched" in risk
        assert "bypass_detected" in risk
        assert risk["lines_added"] == 2
        assert risk["lines_removed"] == 2

    def test_controller_compute_risk_with_bypass(self, minimal_config, event_store, temp_project_dir):
        """Test _compute_risk with bypass detection."""
        controller = ASRController(
            config=minimal_config,
            event_store=event_store,
            project_dir=temp_project_dir
        )

        diff = "--- a/test.py\n+++ b/test.py\n-old\n+pass"
        risk = controller._compute_risk(diff)
        assert risk["bypass_detected"] is True

    def test_controller_lineage_summary(self, minimal_config, event_store, temp_project_dir):
        """Test lineage_summary method."""
        controller = ASRController(
            config=minimal_config,
            event_store=event_store,
            project_dir=temp_project_dir
        )
        controller._patch_lineage.append({"seq": 1, "file": "*", "risk": {"score": 10}})

        lineage = controller.lineage_summary()
        assert len(lineage) == 1
        assert lineage[0]["seq"] == 1

    def test_controller_detect_stable_diff(self, minimal_config, event_store, temp_project_dir):
        """Test _detect_stable_diff method."""
        controller = ASRController(
            config=minimal_config,
            event_store=event_store,
            project_dir=temp_project_dir
        )

        assert controller._detect_stable_diff() is False

        diff = "same diff"
        event = PatchGeneratedEvent(
            task_id="task-1", from_agent=AgentName.BUILDER, to_agent=AgentName.CONTROLLER,
            payload={"diff_text": diff}
        )
        for _ in range(2):
            controller._patch_history.append(event)

        assert controller._detect_stable_diff() is True

    def test_controller_detect_patch_oscillation(self, minimal_config, event_store, temp_project_dir):
        """Test _detect_patch_oscillation method."""
        controller = ASRController(
            config=minimal_config,
            event_store=event_store,
            project_dir=temp_project_dir
        )

        assert controller._detect_patch_oscillation() is False

        diff1 = "diff A"
        diff2 = "diff B"
        for i in range(3):
            diff = diff1 if i % 2 == 0 else diff2
            event = PatchGeneratedEvent(
                task_id="task-1", from_agent=AgentName.BUILDER, to_agent=AgentName.CONTROLLER,
                payload={"diff_text": diff}
            )
            controller._patch_history.append(event)

        assert controller._detect_patch_oscillation() is True


class TestCountFailures:
    """Tests for _count_failures helper function."""

    def test_count_failures_no_failures(self):
        """Test _count_failures with no failures."""
        events = [
            TestPassedEvent(
                task_id="task-1", from_agent=AgentName.TESTER, to_agent=AgentName.CONTROLLER
            )
        ]
        count = _count_failures(events)
        assert count == 0

    def test_count_failures_with_failed_tests(self):
        """Test _count_failures with failed tests."""
        events = [
            TestFailedEvent(
                task_id="task-1", from_agent=AgentName.TESTER, to_agent=AgentName.CONTROLLER,
                payload={"failed": 2, "failures": [{"nodeid": "test_1"}, {"nodeid": "test_2"}]}
            )
        ]
        count = _count_failures(events)
        assert count == 2

    def test_count_failures_with_errors(self):
        """Test _count_failures with test errors."""
        events = [
            TestErrorEvent(
                task_id="task-1", from_agent=AgentName.TESTER, to_agent=AgentName.CONTROLLER
            )
        ]
        count = _count_failures(events)
        assert count == 1

    def test_count_failures_mixed(self):
        """Test _count_failures with mixed events."""
        events = [
            TestFailedEvent(
                task_id="task-1", from_agent=AgentName.TESTER, to_agent=AgentName.CONTROLLER,
                payload={"failed": 1, "failures": [{"nodeid": "test_1"}]}
            ),
            TestErrorEvent(
                task_id="task-1", from_agent=AgentName.TESTER, to_agent=AgentName.CONTROLLER
            )
        ]
        count = _count_failures(events)
        assert count == 2


class TestExpectedTypes:
    """Tests for _EXPECTED_TYPES constant."""

    def test_expected_types_structure(self):
        """Test _EXPECTED_TYPES constant structure."""
        assert "testing" in _EXPECTED_TYPES
        assert "analyzing" in _EXPECTED_TYPES
        assert "repairing" in _EXPECTED_TYPES
        assert "generating" in _EXPECTED_TYPES

    def test_expected_types_testing(self):
        """Test _EXPECTED_TYPES for testing phase."""
        expected = {
            EventType.TEST_FAILED,
            EventType.TEST_PASSED,
            EventType.TEST_ERROR
        }
        assert _EXPECTED_TYPES["testing"] == expected

    def test_expected_types_analyzing(self):
        """Test _EXPECTED_TYPES for analyzing phase."""
        expected = {
            EventType.SPEC_ALIGNED,
            EventType.SPEC_DIFF_FOUND,
            EventType.ANALYZER_FEEDBACK
        }
        assert _EXPECTED_TYPES["analyzing"] == expected

    def test_expected_types_repairing(self):
        """Test _EXPECTED_TYPES for repairing phase."""
        expected = {
            EventType.PATCH_GENERATED,
            EventType.PATCH_APPLIED,
            EventType.PATCH_FAILED
        }
        assert _EXPECTED_TYPES["repairing"] == expected

    def test_expected_types_generating(self):
        """Test _EXPECTED_TYPES for generating phase."""
        expected = {
            EventType.CODE_GENERATED,
        }
        assert _EXPECTED_TYPES["generating"] == expected
