"""Tests for ASR agents module."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import pytest_asyncio

from asr.agents.base import BaseAgent
from asr.agents.builder import BuilderAgent
from asr.agents.tester import TesterAgent
from asr.agents.analyzer import AnalyzerAgent, AnalysisReport
from asr.agents.runner import AgentRunner, AgentOrchestrator
from asr.config.models import AgentConfig, ModelConfig, ASRConfig
from asr.events.models import (
    EventType, AgentName, Event, TaskCreatedEvent, CodeGeneratedEvent,
    TestStartedEvent, TestFailedEvent, TestPassedEvent, SpecDiffFoundEvent,
    SpecAlignedEvent, AnalyzerFeedbackEvent, PatchGeneratedEvent, ErrorOccurredEvent,
)
from asr.events.store import EventStore
from asr.spec.models import Specification


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        (project_dir / "main.py").write_text("print('hello')")
        (project_dir / "DESIGN.md").write_text("# Design Document\nA test system.")
        yield project_dir


@pytest.fixture
def event_store():
    """Create an EventStore instance."""
    return EventStore()


@pytest.fixture
def agent_config():
    """Create a sample agent config."""
    return AgentConfig(role="builder", model=ModelConfig(model="gpt-4o"))


class TestBaseAgent:
    """Tests for BaseAgent."""

    def test_base_agent_initialization(self, event_store):
        """Test BaseAgent initialization."""
        agent = BaseAgent(name=AgentName.BUILDER, event_store=event_store)
        assert agent.name == AgentName.BUILDER
        assert agent._event_store == event_store

    def test_base_agent_name_property(self, event_store):
        """Test BaseAgent.name property."""
        agent = BaseAgent(name=AgentName.TESTER, event_store=event_store)
        assert agent.name == AgentName.TESTER

    def test_base_agent_validate_event_valid(self, event_store):
        """Test BaseAgent.validate_event with valid event."""
        agent = BaseAgent(name=AgentName.BUILDER, event_store=event_store)
        event = TaskCreatedEvent(
            task_id="task-123", from_agent=AgentName.CONTROLLER, to_agent=AgentName.BUILDER
        )
        assert agent.validate_event(event) is True

    def test_base_agent_validate_event_invalid(self, event_store):
        """Test BaseAgent.validate_event with invalid event."""
        agent = BaseAgent(name=AgentName.BUILDER, event_store=event_store)
        event = TaskCreatedEvent(
            task_id="task-123", from_agent=AgentName.CONTROLLER, to_agent=AgentName.TESTER
        )
        assert agent.validate_event(event) is False

    @pytest.mark.asyncio
    async def test_base_agent_emit(self, event_store):
        """Test BaseAgent.emit method."""
        agent = BaseAgent(name=AgentName.BUILDER, event_store=event_store)
        event1 = TaskCreatedEvent(
            task_id="task-123", from_agent=AgentName.CONTROLLER, to_agent=AgentName.BUILDER
        )
        event2 = CodeGeneratedEvent(
            task_id="task-123", from_agent=AgentName.BUILDER, to_agent=AgentName.CONTROLLER
        )

        await agent.emit([event1, event2])

        # Events should be written to event store
        task_events = event_store.get_task_events("task-123")
        assert len(task_events) >= 2

    @pytest.mark.asyncio
    async def test_base_agent_poll_inbox(self, event_store):
        """Test BaseAgent.poll_inbox method."""
        agent = BaseAgent(name=AgentName.TESTER, event_store=event_store)
        event = TaskCreatedEvent(
            task_id="task-123", from_agent=AgentName.CONTROLLER, to_agent=AgentName.TESTER
        )
        event_store.write_event(event)

        events = await agent.poll_inbox()
        assert len(events) == 1
        assert events[0].task_id == "task-123"


class TestBuilderAgent:
    """Tests for BuilderAgent."""

    def test_builder_agent_initialization(self, agent_config, event_store, temp_project_dir):
        """Test BuilderAgent initialization."""
        builder = BuilderAgent(agent_config, event_store, temp_project_dir)
        assert builder.name == AgentName.BUILDER
        assert builder._config == agent_config
        assert builder._project_dir == temp_project_dir
        assert builder._opencode_session_id is None

    @pytest.mark.asyncio
    async def test_builder_process_task_created(self, agent_config, event_store, temp_project_dir):
        """Test BuilderAgent.process with TASK_CREATED event."""
        builder = BuilderAgent(agent_config, event_store, temp_project_dir)
        spec = Specification(goal="Build a system")
        event = TaskCreatedEvent(
            task_id="task-123",
            from_agent=AgentName.CONTROLLER,
            to_agent=AgentName.BUILDER,
            payload={"spec": spec.model_dump()}
        )

        with patch.object(builder, '_call_opencode', return_value="diff content"):
            events = await builder.process(event)
            assert len(events) == 1
            assert events[0].type == EventType.CODE_GENERATED

    @pytest.mark.asyncio
    async def test_builder_process_invalid_agent(self, agent_config, event_store, temp_project_dir):
        """Test BuilderAgent.process with wrong target agent."""
        builder = BuilderAgent(agent_config, event_store, temp_project_dir)
        event = TaskCreatedEvent(
            task_id="task-123",
            from_agent=AgentName.CONTROLLER,
            to_agent=AgentName.TESTER  # Wrong agent
        )

        events = await builder.process(event)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_builder_process_patch_generated(self, agent_config, event_store, temp_project_dir):
        """Test BuilderAgent.process with PATCH_GENERATED event."""
        builder = BuilderAgent(agent_config, event_store, temp_project_dir)
        failures = [{"nodeid": "test_1", "message": "AssertionError"}]
        event = PatchGeneratedEvent(
            task_id="task-123",
            from_agent=AgentName.CONTROLLER,
            to_agent=AgentName.BUILDER,
            payload={"failures": failures}
        )

        with patch.object(builder, '_call_opencode', return_value="patch diff"):
            events = await builder.process(event)
            assert len(events) == 1
            assert events[0].type == EventType.PATCH_GENERATED

    @pytest.mark.asyncio
    async def test_builder_process_test_failed(self, agent_config, event_store, temp_project_dir):
        """Test BuilderAgent.process with TEST_FAILED event."""
        builder = BuilderAgent(agent_config, event_store, temp_project_dir)
        failures = [{"nodeid": "test_1", "message": "AssertionError"}]
        event = TestFailedEvent(
            task_id="task-123",
            from_agent=AgentName.TESTER,
            to_agent=AgentName.BUILDER,
            payload={"failures": failures}
        )

        with patch.object(builder, '_call_opencode', return_value="fix diff"):
            events = await builder.process(event)
            assert len(events) == 1
            assert events[0].type == EventType.PATCH_GENERATED

    @pytest.mark.asyncio
    async def test_builder_process_error_occurred(self, agent_config, event_store, temp_project_dir):
        """Test BuilderAgent.process exception handling."""
        builder = BuilderAgent(agent_config, event_store, temp_project_dir)
        event = TaskCreatedEvent(
            task_id="task-123",
            from_agent=AgentName.CONTROLLER,
            to_agent=AgentName.BUILDER
        )

        with patch.object(builder, '_call_opencode', side_effect=Exception("Test error")):
            events = await builder.process(event)
            assert len(events) == 1
            assert events[0].type == EventType.ERROR_OCCURRED

    def test_builder_build_task_prompt(self, agent_config, event_store, temp_project_dir):
        """Test BuilderAgent._build_task_prompt method."""
        builder = BuilderAgent(agent_config, event_store, temp_project_dir)
        prompt = builder._build_task_prompt()
        assert "DESIGN.md" in prompt
        assert "可研报告" in prompt
        assert "### DONE" in prompt

    def test_builder_build_patch_prompt_with_failures(self, agent_config, event_store, temp_project_dir):
        """Test BuilderAgent._build_patch_prompt with failures."""
        builder = BuilderAgent(agent_config, event_store, temp_project_dir)
        failures = [
            {"nodeid": "test_1", "message": "Error 1"},
            {"nodeid": "test_2", "message": "Error 2"}
        ]
        prompt = builder._build_patch_prompt(failures, [])
        assert "修复以下测试失败" in prompt
        assert "test_1" in prompt or "Error 1" in prompt
        assert "### DONE" in prompt

    def test_builder_build_patch_prompt_with_feedback(self, agent_config, event_store, temp_project_dir):
        """Test BuilderAgent._build_patch_prompt with feedback."""
        builder = BuilderAgent(agent_config, event_store, temp_project_dir)
        feedback = ["Issue 1", "Issue 2"]
        prompt = builder._build_patch_prompt([], feedback)
        assert "修复以下偏差" in prompt
        assert "Issue 1" in prompt
        assert "### DONE" in prompt

    def test_builder_build_patch_prompt_no_feedback(self, agent_config, event_store, temp_project_dir):
        """Test BuilderAgent._build_patch_prompt with no feedback."""
        builder = BuilderAgent(agent_config, event_store, temp_project_dir)
        prompt = builder._build_patch_prompt([], [])
        assert "### DONE" in prompt


class TestTesterAgent:
    """Tests for TesterAgent."""

    def test_tester_agent_initialization(self, agent_config, event_store, temp_project_dir):
        """Test TesterAgent initialization."""
        tester = TesterAgent(agent_config, event_store, temp_project_dir)
        assert tester.name == AgentName.TESTER
        assert tester._config == agent_config
        assert tester._project_dir == temp_project_dir

    @pytest.mark.asyncio
    async def test_tester_process_test_started_no_code(self, agent_config, event_store, temp_project_dir):
        """Test TesterAgent.process with no Python files."""
        tester = TesterAgent(agent_config, event_store, temp_project_dir)
        for py_file in temp_project_dir.glob("*.py"):
            py_file.unlink()

        event = TestStartedEvent(
            task_id="task-123",
            from_agent=AgentName.CONTROLLER,
            to_agent=AgentName.TESTER
        )

        events = await tester.process(event)
        assert len(events) == 1
        assert events[0].type == EventType.TEST_FAILED
        assert "No Python files" in events[0].payload.get("failures", [{}])[0].get("message", "")

    @pytest.mark.asyncio
    async def test_tester_process_invalid_agent(self, agent_config, event_store, temp_project_dir):
        """Test TesterAgent.process with wrong target agent."""
        tester = TesterAgent(agent_config, event_store, temp_project_dir)
        event = TestStartedEvent(
            task_id="task-123",
            from_agent=AgentName.CONTROLLER,
            to_agent=AgentName.BUILDER  # Wrong agent
        )
        events = await tester.process(event)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_tester_process_error_occurred(self, agent_config, event_store, temp_project_dir):
        """Test TesterAgent.process exception handling."""
        tester = TesterAgent(agent_config, event_store, temp_project_dir)
        event = TestStartedEvent(
            task_id="task-123",
            from_agent=AgentName.CONTROLLER,
            to_agent=AgentName.TESTER
        )

        with patch('asr.agents.tester.opencode_completion', side_effect=Exception("Test error")):
            events = await tester.process(event)
            assert len(events) == 1
            assert events[0].type == EventType.ERROR_OCCURRED


class TestAnalyzerAgent:
    """Tests for AnalyzerAgent."""

    def test_analyzer_agent_initialization(self, agent_config, event_store, temp_project_dir):
        """Test AnalyzerAgent initialization."""
        analyzer = AnalyzerAgent(agent_config, event_store, temp_project_dir)
        assert analyzer.name == AgentName.ANALYZER
        assert analyzer._config == agent_config
        assert analyzer._project_dir == temp_project_dir

    @pytest.mark.asyncio
    async def test_analyzer_process_spec_diff_found_not_aligned(self, agent_config, event_store, temp_project_dir):
        """Test AnalyzerAgent.process with issues found."""
        analyzer = AnalyzerAgent(agent_config, event_store, temp_project_dir)
        event = SpecDiffFoundEvent(
            task_id="task-123",
            from_agent=AgentName.CONTROLLER,
            to_agent=AgentName.ANALYZER
        )

        report = AnalysisReport(
            aligned=False,
            missing_features=["feature1"],
            logic_issues=["issue1"],
            constraint_violations=["violation1"]
        )

        with patch.object(analyzer, '_analyze', return_value=report):
            events = await analyzer.process(event)
            assert len(events) == 2
            assert events[0].type == EventType.SPEC_DIFF_FOUND
            assert events[1].type == EventType.ANALYZER_FEEDBACK

    @pytest.mark.asyncio
    async def test_analyzer_process_spec_diff_found_aligned(self, agent_config, event_store, temp_project_dir):
        """Test AnalyzerAgent.process with aligned spec."""
        analyzer = AnalyzerAgent(agent_config, event_store, temp_project_dir)
        event = SpecDiffFoundEvent(
            task_id="task-123",
            from_agent=AgentName.CONTROLLER,
            to_agent=AgentName.ANALYZER
        )

        report = AnalysisReport(aligned=True)

        with patch.object(analyzer, '_analyze', return_value=report):
            events = await analyzer.process(event)
            assert len(events) == 1
            assert events[0].type == EventType.SPEC_ALIGNED

    @pytest.mark.asyncio
    async def test_analyzer_process_invalid_agent(self, agent_config, event_store, temp_project_dir):
        """Test AnalyzerAgent.process with wrong target agent."""
        analyzer = AnalyzerAgent(agent_config, event_store, temp_project_dir)
        event = SpecDiffFoundEvent(
            task_id="task-123",
            from_agent=AgentName.CONTROLLER,
            to_agent=AgentName.BUILDER  # Wrong agent
        )
        events = await analyzer.process(event)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_analyzer_process_error_occurred(self, agent_config, event_store, temp_project_dir):
        """Test AnalyzerAgent.process exception handling."""
        analyzer = AnalyzerAgent(agent_config, event_store, temp_project_dir)
        event = SpecDiffFoundEvent(
            task_id="task-123",
            from_agent=AgentName.CONTROLLER,
            to_agent=AgentName.ANALYZER
        )

        with patch.object(analyzer, '_analyze', side_effect=Exception("Test error")):
            events = await analyzer.process(event)
            assert len(events) == 1
            assert events[0].type == EventType.ERROR_OCCURRED

    def test_analyzer_extract_descriptions(self, agent_config, event_store, temp_project_dir):
        """Test AnalyzerAgent._extract_descriptions method."""
        analyzer = AnalyzerAgent(agent_config, event_store, temp_project_dir)

        items = ["item1", {"description": "item2"}, {"description": "item3", "severity": "high"}]
        result = analyzer._extract_descriptions(items)

        assert len(result) == 3
        assert "item1" in result
        assert "item2" in result
        assert "[high] item3" in result


class TestAnalysisReport:
    """Tests for AnalysisReport dataclass."""

    def test_analysis_report_defaults(self):
        """Test AnalysisReport with default values."""
        report = AnalysisReport()
        assert report.aligned is False
        assert report.task_type == "bugfix"
        assert report.missing_features == []
        assert report.logic_issues == []
        assert report.constraint_violations == []
        assert report.high_severity_count == 0

    def test_analysis_report_with_issues(self):
        """Test AnalysisReport with issues."""
        report = AnalysisReport(
            aligned=False,
            task_type="dev",
            missing_features=["feature1"],
            logic_issues=["issue1"],
            constraint_violations=["violation1"],
            high_severity_count=2
        )
        assert report.aligned is False
        assert report.task_type == "dev"
        assert len(report.missing_features) == 1
        assert len(report.logic_issues) == 1
        assert len(report.constraint_violations) == 1
        assert report.high_severity_count == 2

    def test_analysis_report_aligned(self):
        """Test AnalysisReport when aligned."""
        report = AnalysisReport(aligned=True)
        assert report.aligned is True


class TestAgentRunner:
    """Tests for AgentRunner."""

    @pytest.fixture
    def mock_agent(self, event_store):
        """Create a mock agent for testing."""
        class MockAgent(BaseAgent):
            def __init__(self, event_store):
                super().__init__(name=AgentName.BUILDER, event_store=event_store)
                self.processed_events = []

            async def process(self, event):
                self.processed_events.append(event)
                return [Event(
                    task_id=event.task_id,
                    type=EventType.CODE_GENERATED,
                    from_agent=AgentName.BUILDER,
                    to_agent=AgentName.CONTROLLER
                )]
        return MockAgent(event_store)

    def test_agent_runner_initialization(self, mock_agent, event_store):
        """Test AgentRunner initialization."""
        runner = AgentRunner(mock_agent, event_store)
        assert runner.agent == mock_agent
        assert runner._event_store == event_store
        assert runner._poll_interval == 0.1
        assert runner._task is None
        assert not runner._running

    def test_agent_runner_custom_interval(self, mock_agent, event_store):
        """Test AgentRunner with custom poll interval."""
        runner = AgentRunner(mock_agent, event_store, poll_interval=0.5)
        assert runner._poll_interval == 0.5

    @pytest.mark.asyncio
    async def test_agent_runner_start_and_stop(self, mock_agent, event_store):
        """Test AgentRunner start and stop methods."""
        runner = AgentRunner(mock_agent, event_store)
        await runner.start()
        assert runner._running is True
        assert runner._task is not None

        await runner.stop()
        assert runner._running is False

    @pytest.mark.asyncio
    async def test_agent_runner_poll_loop(self, mock_agent, event_store):
        """Test AgentRunner poll loop."""
        runner = AgentRunner(mock_agent, event_store, poll_interval=0.01)

        start_event = TaskCreatedEvent(
            task_id="task-123", from_agent=AgentName.CONTROLLER, to_agent=AgentName.BUILDER
        )
        event_store.write_event(start_event)

        await runner.start()
        await asyncio.sleep(0.1)  # Give time for poll loop to process
        await runner.stop()

        assert len(mock_agent.processed_events) >= 1


class TestAgentOrchestrator:
    """Tests for AgentOrchestrator."""

    @pytest.fixture
    def mock_runner(self, event_store):
        """Create a mock runner for testing."""
        class MockRunner:
            def __init__(self, event_store):
                self.event_store = event_store
                self.running = False

            async def start(self):
                self.running = True

            async def stop(self):
                self.running = False
        return MockRunner(event_store)

    def test_orchestrator_initialization(self, event_store):
        """Test AgentOrchestrator initialization."""
        orchestrator = AgentOrchestrator(event_store)
        assert orchestrator._event_store == event_store
        assert orchestrator._runners == {}

    def test_orchestrator_register(self, event_store, mock_runner):
        """Test AgentOrchestrator.register method."""
        orchestrator = AgentOrchestrator(event_store)
        orchestrator.register("builder", mock_runner)
        assert "builder" in orchestrator._runners
        assert orchestrator._runners["builder"] == mock_runner

    @pytest.mark.asyncio
    async def test_orchestrator_start_all(self, event_store, mock_runner):
        """Test AgentOrchestrator.start_all method."""
        orchestrator = AgentOrchestrator(event_store)
        orchestrator.register("builder", mock_runner)
        orchestrator.register("tester", mock_runner)

        await orchestrator.start_all()
        assert mock_runner.running is True

    @pytest.mark.asyncio
    async def test_orchestrator_stop_all(self, event_store, mock_runner):
        """Test AgentOrchestrator.stop_all method."""
        orchestrator = AgentOrchestrator(event_store)
        orchestrator.register("builder", mock_runner)

        await orchestrator.start_all()
        await orchestrator.stop_all()
        assert mock_runner.running is False

    @pytest.mark.asyncio
    async def test_orchestrator_run_until_converged(self, event_store):
        """Test AgentOrchestrator.run_until_converged method."""
        orchestrator = AgentOrchestrator(event_store)

        async def controller_coro():
            return {"status": "converged"}

        result = await orchestrator.run_until_converged(controller_coro, max_wait=1.0)
        assert result == {"status": "converged"}
