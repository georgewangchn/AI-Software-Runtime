"""Tests for ASR event models and event store."""

import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest

from asr.events.models import (
    EventType, AgentName,
    Event, TaskCreatedEvent, CodeGeneratedEvent, TestStartedEvent,
    TestFailedEvent, TestPassedEvent, TestErrorEvent, SpecDiffFoundEvent,
    SpecAlignedEvent, PatchGeneratedEvent, PatchAppliedEvent, PatchFailedEvent,
    PatchRolledBackEvent, AnalyzerFeedbackEvent, ConvergenceIterationEvent,
    ConvergedEvent, StuckEvent, ErrorOccurredEvent, MeshVerdictEvent,
    event_from_dict,
)
from asr.events.store import EventStore


def test_event_type_enum():
    """Test EventType enum values."""
    assert EventType.TASK_CREATED == "task_created"
    assert EventType.CODE_GENERATED == "code_generated"
    assert EventType.TEST_FAILED == "test_failed"
    assert EventType.TEST_PASSED == "test_passed"
    assert EventType.CONVERGED == "converged"
    assert EventType.STUCK == "stuck"


def test_agent_name_enum():
    """Test AgentName enum values."""
    assert AgentName.BUILDER == "builder"
    assert AgentName.TESTER == "tester"
    assert AgentName.ANALYZER == "analyzer"
    assert AgentName.CONTROLLER == "controller"
    assert AgentName.SYSTEM == "system"


def test_event_defaults():
    """Test Event with default values."""
    event = Event(
        task_id="task-123",
        type=EventType.TASK_CREATED,
        from_agent=AgentName.CONTROLLER,
        to_agent=AgentName.BUILDER
    )
    assert event.task_id == "task-123"
    assert event.type == EventType.TASK_CREATED
    assert event.from_agent == AgentName.CONTROLLER
    assert event.to_agent == AgentName.BUILDER
    assert len(event.event_id) > 0
    assert event.timestamp is not None
    assert event.sequence == 1


def test_event_custom_fields():
    """Test Event with custom event_id and timestamp."""
    custom_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    event = Event(
        event_id="custom-id-123",
        task_id="task-123",
        type=EventType.TASK_CREATED,
        from_agent=AgentName.CONTROLLER,
        to_agent=AgentName.BUILDER,
        timestamp=custom_time,
        sequence=5
    )
    assert event.event_id == "custom-id-123"
    assert event.timestamp == custom_time
    assert event.sequence == 5


def test_task_created_event():
    """Test TaskCreatedEvent."""
    payload = {"spec_path": "/path/to/spec.yaml", "project_path": "/project"}
    event = TaskCreatedEvent(
        task_id="task-123",
        from_agent=AgentName.CONTROLLER,
        to_agent=AgentName.BUILDER,
        payload=payload
    )
    assert event.type == EventType.TASK_CREATED
    assert event.payload == payload


def test_code_generated_event():
    """Test CodeGeneratedEvent."""
    payload = {"files_modified": ["main.py"], "diff_text": "..."}
    event = CodeGeneratedEvent(
        task_id="task-123",
        from_agent=AgentName.BUILDER,
        to_agent=AgentName.CONTROLLER,
        payload=payload
    )
    assert event.type == EventType.CODE_GENERATED
    assert event.payload == payload


def test_test_started_event():
    """Test TestStartedEvent."""
    payload = {"test_paths": ["/project/tests"]}
    event = TestStartedEvent(
        task_id="task-123",
        from_agent=AgentName.CONTROLLER,
        to_agent=AgentName.TESTER,
        payload=payload
    )
    assert event.type == EventType.TEST_STARTED
    assert event.payload == payload


def test_test_failed_event():
    """Test TestFailedEvent."""
    payload = {
        "total": 10,
        "passed": 8,
        "failed": 2,
        "errors": 0,
        "failures": [{"nodeid": "test_example", "message": "AssertionError"}]
    }
    event = TestFailedEvent(
        task_id="task-123",
        from_agent=AgentName.TESTER,
        to_agent=AgentName.CONTROLLER,
        payload=payload
    )
    assert event.type == EventType.TEST_FAILED
    assert event.payload == payload


def test_test_passed_event():
    """Test TestPassedEvent."""
    payload = {"total": 10, "passed": 10, "duration": 5.5}
    event = TestPassedEvent(
        task_id="task-123",
        from_agent=AgentName.TESTER,
        to_agent=AgentName.CONTROLLER,
        payload=payload
    )
    assert event.type == EventType.TEST_PASSED
    assert event.payload == payload


def test_test_error_event():
    """Test TestErrorEvent."""
    payload = {"error_message": "ImportError: module not found", "exit_code": 1}
    event = TestErrorEvent(
        task_id="task-123",
        from_agent=AgentName.TESTER,
        to_agent=AgentName.CONTROLLER,
        payload=payload
    )
    assert event.type == EventType.TEST_ERROR
    assert event.payload == payload


def test_spec_diff_found_event():
    """Test SpecDiffFoundEvent."""
    payload = {
        "missing_features": ["feature1"],
        "logic_issues": ["logical error"],
        "constraint_violations": ["violation1"]
    }
    event = SpecDiffFoundEvent(
        task_id="task-123",
        from_agent=AgentName.ANALYZER,
        to_agent=AgentName.CONTROLLER,
        payload=payload
    )
    assert event.type == EventType.SPEC_DIFF_FOUND
    assert event.payload == payload


def test_spec_aligned_event():
    """Test SpecAlignedEvent."""
    payload = {"findings": ["all good"]}
    event = SpecAlignedEvent(
        task_id="task-123",
        from_agent=AgentName.ANALYZER,
        to_agent=AgentName.CONTROLLER,
        payload=payload
    )
    assert event.type == EventType.SPEC_ALIGNED
    assert event.payload == payload


def test_patch_generated_event():
    """Test PatchGeneratedEvent."""
    payload = {"file_path": "main.py", "diff_text": "...", "reason": "fix bug"}
    event = PatchGeneratedEvent(
        task_id="task-123",
        from_agent=AgentName.BUILDER,
        to_agent=AgentName.CONTROLLER,
        payload=payload
    )
    assert event.type == EventType.PATCH_GENERATED
    assert event.payload == payload


def test_patch_applied_event():
    """Test PatchAppliedEvent."""
    payload = {"file_path": "main.py", "success": True, "error": None}
    event = PatchAppliedEvent(
        task_id="task-123",
        from_agent=AgentName.BUILDER,
        to_agent=AgentName.CONTROLLER,
        payload=payload
    )
    assert event.type == EventType.PATCH_APPLIED
    assert event.payload == payload


def test_patch_failed_event():
    """Test PatchFailedEvent."""
    payload = {"file_path": "main.py", "error": "diff mismatch", "failed_hunk": 1}
    event = PatchFailedEvent(
        task_id="task-123",
        from_agent=AgentName.BUILDER,
        to_agent=AgentName.CONTROLLER,
        payload=payload
    )
    assert event.type == EventType.PATCH_FAILED
    assert event.payload == payload


def test_patch_rolled_back_event():
    """Test PatchRolledBackEvent."""
    payload = {"file_path": "main.py", "reason": "roll back due to failure"}
    event = PatchRolledBackEvent(
        task_id="task-123",
        from_agent=AgentName.CONTROLLER,
        to_agent=AgentName.BUILDER,
        payload=payload
    )
    assert event.type == EventType.PATCH_ROLLED_BACK
    assert event.payload == payload


def test_analyzer_feedback_event():
    """Test AnalyzerFeedbackEvent."""
    payload = {"findings": ["issue1"], "recommendation": "fix it"}
    event = AnalyzerFeedbackEvent(
        task_id="task-123",
        from_agent=AgentName.ANALYZER,
        to_agent=AgentName.BUILDER,
        payload=payload
    )
    assert event.type == EventType.ANALYZER_FEEDBACK
    assert event.payload == payload


def test_convergence_iteration_event():
    """Test ConvergenceIterationEvent."""
    payload = {"iteration": 3, "errors_remaining": 2}
    event = ConvergenceIterationEvent(
        task_id="task-123",
        from_agent=AgentName.CONTROLLER,
        to_agent=AgentName.SYSTEM,
        payload=payload
    )
    assert event.type == EventType.CONVERGENCE_ITERATION
    assert event.payload == payload


def test_converged_event():
    """Test ConvergedEvent."""
    payload = {"total_iterations": 5, "final_test_results": {"passed": True}}
    event = ConvergedEvent(
        task_id="task-123",
        from_agent=AgentName.CONTROLLER,
        to_agent=AgentName.SYSTEM,
        payload=payload
    )
    assert event.type == EventType.CONVERGED
    assert event.payload == payload


def test_stuck_event():
    """Test StuckEvent."""
    payload = {"reason": "max_iterations", "last_iteration": 10, "errors_remaining": 3}
    event = StuckEvent(
        task_id="task-123",
        from_agent=AgentName.CONTROLLER,
        to_agent=AgentName.SYSTEM,
        payload=payload
    )
    assert event.type == EventType.STUCK
    assert event.payload == payload


def test_error_occurred_event():
    """Test ErrorOccurredEvent."""
    payload = {
        "agent": "builder",
        "error_type": "ValueError",
        "error_message": "invalid value",
        "retry_hint": "retryable"
    }
    event = ErrorOccurredEvent(
        task_id="task-123",
        from_agent=AgentName.BUILDER,
        to_agent=AgentName.CONTROLLER,
        payload=payload
    )
    assert event.type == EventType.ERROR_OCCURRED
    assert event.payload == payload


def test_mesh_verdict_event():
    """Test MeshVerdictEvent."""
    payload = {
        "agent": "security",
        "severity": "high",
        "finding": "security issue found",
        "passed": False
    }
    event = MeshVerdictEvent(
        task_id="task-123",
        from_agent=AgentName.SECURITY,
        to_agent=AgentName.CONTROLLER,
        payload=payload
    )
    assert event.type == EventType.MESH_VERDICT
    assert event.payload == payload


def test_event_serialization():
    """Test Event serialization to JSON."""
    event = TaskCreatedEvent(
        task_id="task-123",
        from_agent=AgentName.CONTROLLER,
        to_agent=AgentName.BUILDER,
        payload={"project_path": "/test"}
    )
    json_str = event.model_dump_json()
    data = json.loads(json_str)
    assert data["task_id"] == "task-123"
    assert data["type"] == "task_created"


def test_event_from_dict():
    """Test event_from_dict function."""
    data = {
        "event_id": "event-123",
        "task_id": "task-123",
        "type": "task_created",
        "from_agent": "controller",
        "to_agent": "builder",
        "timestamp": "2024-01-01T12:00:00",
        "sequence": 1,
        "payload": {}
    }
    event = event_from_dict(data)
    assert isinstance(event, TaskCreatedEvent)
    assert event.event_id == "event-123"
    assert event.task_id == "task-123"


def test_event_from_dict_unknown_type():
    """Test event_from_dict with unknown event type."""
    data = {
        "event_id": "event-123",
        "task_id": "task-123",
        "type": "unknown_type",
        "from_agent": "controller",
        "to_agent": "builder",
        "payload": {}
    }
    event = event_from_dict(data)
    assert isinstance(event, Event)
    assert not isinstance(event, TaskCreatedEvent)


@pytest.fixture
def temp_event_dir():
    """Create a temporary directory for event storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_event_store_initialization(temp_event_dir):
    """Test EventStore initialization."""
    store = EventStore(event_dir=temp_event_dir)
    assert Path(temp_event_dir).exists()
    assert Path(".runtime/patches").exists()
    assert Path(".runtime/diffs").exists()
    assert Path(".runtime/state").exists()
    assert Path(".runtime/tasks").exists()


def test_event_store_write_and_read(temp_event_dir):
    """Test EventStore write and read operations."""
    store = EventStore(event_dir=temp_event_dir)
    event = TaskCreatedEvent(
        task_id="task-123",
        from_agent=AgentName.CONTROLLER,
        to_agent=AgentName.BUILDER,
        payload={"project_path": "/test"}
    )

    path = store.write_event(event)
    assert Path(path).exists()

    read_event = store.read_event(event.event_id)
    assert read_event.task_id == event.task_id
    assert read_event.event_id == event.event_id


def test_event_store_get_task_events(temp_event_dir):
    """Test EventStore.get_task_events."""
    store = EventStore(event_dir=temp_event_dir)
    task_id = "task-123"

    event1 = TaskCreatedEvent(task_id=task_id, from_agent=AgentName.CONTROLLER, to_agent=AgentName.BUILDER)
    event2 = CodeGeneratedEvent(task_id=task_id, from_agent=AgentName.BUILDER, to_agent=AgentName.CONTROLLER)
    event3 = TaskCreatedEvent(task_id="other-task", from_agent=AgentName.CONTROLLER, to_agent=AgentName.BUILDER)

    store.write_event(event1)
    store.write_event(event2)
    store.write_event(event3)

    events = store.get_task_events(task_id)
    assert len(events) == 2
    assert all(e.task_id == task_id for e in events)


def test_event_store_replay_events(temp_event_dir):
    """Test EventStore.replay_events."""
    store = EventStore(event_dir=temp_event_dir)
    task_id = "task-123"

    event1 = TaskCreatedEvent(task_id=task_id, from_agent=AgentName.CONTROLLER, to_agent=AgentName.BUILDER)
    event2 = CodeGeneratedEvent(task_id=task_id, from_agent=AgentName.BUILDER, to_agent=AgentName.CONTROLLER)

    store.write_event(event1)
    store.write_event(event2)

    replayed = store.replay_events(task_id)
    assert len(replayed) == 2


def test_event_store_save_patch(temp_event_dir):
    """Test EventStore.save_patch."""
    store = EventStore(event_dir=temp_event_dir)
    task_id = "task-123"
    diff_text = "--- a/file.py\n+++ b/file.py\n@@ -1,1 +1,1 @@\n-old\n+new"

    path = store.save_patch(task_id, diff_text, "file.py")
    assert Path(path).exists()
    content = Path(path).read_text()
    assert content == diff_text


def test_event_store_save_diff(temp_event_dir):
    """Test EventStore.save_diff."""
    store = EventStore(event_dir=temp_event_dir)
    task_id = "task-123"
    diff_text = "diff content"

    patch_dir = Path(".runtime/diffs")
    patch_dir.mkdir(parents=True, exist_ok=True)

    path = store.save_diff(task_id, diff_text)
    assert Path(path).exists()
    content = Path(path).read_text()
    assert content == diff_text


def test_event_store_save_task_state(temp_event_dir):
    """Test EventStore.save_task_state."""
    store = EventStore(event_dir=temp_event_dir)
    task_id = "task-123"
    state = {"iteration": 5, "status": "converged"}

    tasks_dir = Path(".runtime/tasks")
    tasks_dir.mkdir(parents=True, exist_ok=True)

    path = store.save_task_state(task_id, state)
    assert Path(path).exists()
    content = json.loads(Path(path).read_text())
    assert content["iteration"] == 5
    assert content["status"] == "converged"
