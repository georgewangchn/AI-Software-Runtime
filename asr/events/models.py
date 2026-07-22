from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    TASK_CREATED = "task_created"
    CODE_GENERATED = "code_generated"
    TEST_STARTED = "test_started"
    TEST_FAILED = "test_failed"
    TEST_PASSED = "test_passed"
    TEST_ERROR = "test_error"
    SPEC_DIFF_FOUND = "spec_diff_found"
    SPEC_ALIGNED = "spec_aligned"
    PATCH_REQUESTED = "patch_requested"
    PATCH_GENERATED = "patch_generated"
    PATCH_APPLIED = "patch_applied"
    PATCH_FAILED = "patch_failed"
    PATCH_ROLLED_BACK = "patch_rolled_back"
    ANALYZE_REQUESTED = "analyze_requested"
    ANALYZER_FEEDBACK = "analyzer_feedback"
    CONVERGENCE_ITERATION = "convergence_iteration"
    CONVERGED = "converged"
    STUCK = "stuck"
    ERROR_OCCURRED = "error_occurred"
    CONVERGENCE_METRICS = "convergence_metrics"


class AgentName(str, Enum):
    BUILDER = "builder"
    TESTER = "tester"
    ANALYZER = "analyzer"
    CONTROLLER = "controller"
    SYSTEM = "system"


class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    type: EventType
    from_agent: AgentName
    to_agent: AgentName
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = 1


class TaskCreatedEvent(Event):
    type: EventType = EventType.TASK_CREATED
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: spec_path, project_path, max_iterations


class CodeGeneratedEvent(Event):
    type: EventType = EventType.CODE_GENERATED
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: summary {files, added, removed, bypass_detected, risk_score}


class TestStartedEvent(Event):
    type: EventType = EventType.TEST_STARTED
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: test_paths


class TestFailedEvent(Event):
    type: EventType = EventType.TEST_FAILED
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: total, passed, failed, errors, failures


class TestPassedEvent(Event):
    type: EventType = EventType.TEST_PASSED
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: total, passed, duration


class TestErrorEvent(Event):
    type: EventType = EventType.TEST_ERROR
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: error_message, exit_code


class SpecDiffFoundEvent(Event):
    type: EventType = EventType.SPEC_DIFF_FOUND
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: missing_features, logic_issues, constraint_violations (response)


class AnalyzeRequestedEvent(Event):
    type: EventType = EventType.ANALYZE_REQUESTED
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: project_path, test_summary (request)


class SpecAlignedEvent(Event):
    type: EventType = EventType.SPEC_ALIGNED
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: findings


class PatchGeneratedEvent(Event):
    type: EventType = EventType.PATCH_GENERATED
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: summary, reason


class PatchRequestedEvent(Event):
    type: EventType = EventType.PATCH_REQUESTED
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: failures, feedback, project_path


class PatchAppliedEvent(Event):
    type: EventType = EventType.PATCH_APPLIED
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: file_path, success, error


class PatchFailedEvent(Event):
    type: EventType = EventType.PATCH_FAILED
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: file_path, error, failed_hunk


class PatchRolledBackEvent(Event):
    type: EventType = EventType.PATCH_ROLLED_BACK
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: file_path, reason


class AnalyzerFeedbackEvent(Event):
    type: EventType = EventType.ANALYZER_FEEDBACK
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: findings, recommendation


class ConvergenceIterationEvent(Event):
    type: EventType = EventType.CONVERGENCE_ITERATION
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: iteration, errors_remaining


class ConvergedEvent(Event):
    type: EventType = EventType.CONVERGED
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: total_iterations, final_test_results


class StuckEvent(Event):
    type: EventType = EventType.STUCK
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: reason, last_iteration, errors_remaining


class ErrorOccurredEvent(Event):
    type: EventType = EventType.ERROR_OCCURRED
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: agent, error_type, error_message, retry_hint


class ConvergenceMetrics(BaseModel):
    """显式控制指标：每一轮迭代的统一误差信号。"""
    iteration: int = 0
    # 硬约束信号
    test_failed_count: int = 0
    test_error_count: int = 0
    # 语义信号
    missing_feature_count: int = 0
    logic_issue_count: int = 0
    constraint_violation_count: int = 0
    high_severity_count: int = 0
    # patch 信号
    patch_count: int = 0
    changed_file_count: int = 0
    changed_line_count: int = 0
    # 稳定性信号
    rollback_count: int = 0
    repeated_failure_count: int = 0
    oscillation_score: float = 0.0
    # 测试通过率（地面真值，优先级高于 error_score）
    test_pass_rate: float = 0.0   # 0.0~1.0，地面真值
    # 统一误差分数（可配置权重，含噪声的 Analyzer 信号）
    error_score: float = 0.0
    # 趋势（基于 test_pass_rate 计算，不依赖噪声信号）
    trend: str = "unknown"  # "improving" | "stalled" | "regressing" | "oscillating"
    # P1-1: 双传感器交叉验证
    sensor_disagreement: str = "AGREED"  # "AGREED" | "INCOMPLETE_TESTS" | "TEST_QUALITY_ISSUE"


class ConvergenceMetricsEvent(Event):
    type: EventType = EventType.CONVERGENCE_METRICS
    payload: dict[str, Any] = Field(default_factory=dict)
    # payload keys: metrics (ConvergenceMetrics dict), trend, error_score, previous_error_score


_EVENT_TYPE_MAP: dict[EventType, type[Event]] = {
    EventType.TASK_CREATED: TaskCreatedEvent,
    EventType.CODE_GENERATED: CodeGeneratedEvent,
    EventType.TEST_STARTED: TestStartedEvent,
    EventType.TEST_FAILED: TestFailedEvent,
    EventType.TEST_PASSED: TestPassedEvent,
    EventType.TEST_ERROR: TestErrorEvent,
    EventType.SPEC_DIFF_FOUND: SpecDiffFoundEvent,
    EventType.SPEC_ALIGNED: SpecAlignedEvent,
    EventType.PATCH_REQUESTED: PatchRequestedEvent,
    EventType.PATCH_GENERATED: PatchGeneratedEvent,
    EventType.PATCH_APPLIED: PatchAppliedEvent,
    EventType.PATCH_FAILED: PatchFailedEvent,
    EventType.PATCH_ROLLED_BACK: PatchRolledBackEvent,
    EventType.ANALYZE_REQUESTED: AnalyzeRequestedEvent,
    EventType.ANALYZER_FEEDBACK: AnalyzerFeedbackEvent,
    EventType.CONVERGENCE_ITERATION: ConvergenceIterationEvent,
    EventType.CONVERGED: ConvergedEvent,
    EventType.STUCK: StuckEvent,
    EventType.ERROR_OCCURRED: ErrorOccurredEvent,
    EventType.CONVERGENCE_METRICS: ConvergenceMetricsEvent,
}


def event_from_dict(data: dict[str, Any]) -> Event:
    event_type = EventType(data["type"])
    event_cls = _EVENT_TYPE_MAP.get(event_type, Event)
    return event_cls(**data)
