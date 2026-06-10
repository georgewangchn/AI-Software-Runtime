"""Tests for ASR runtime module."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from asr.runtime import ASRRuntime
from asr.config.models import ASRConfig, ConvergenceConfig, AgentConfig, ModelConfig
from asr.controller.convergence import ConvergenceState, ConvergenceResult
from asr.spec.models import Specification


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        (project_dir / "main.py").write_text("print('hello')")
        (project_dir / "DESIGN.md").write_text("# Design\nTest system.")
        yield project_dir


@pytest.fixture
def spec_path(temp_project_dir):
    """Create a spec.yaml file."""
    spec_file = temp_project_dir / "spec.yaml"
    spec_file.write_text("goal: Build system")
    return spec_file


@pytest.fixture
def minimal_config():
    """Create minimal ASR config."""
    return ASRConfig()


class TestASRRuntime:
    """Tests for ASRRuntime class."""

    def test_runtime_initialization(self, minimal_config):
        """Test ASRRuntime initialization."""
        runtime = ASRRuntime(minimal_config)
        assert runtime._config == minimal_config
        assert runtime._event_store is not None

    def test_runtime_default_config(self):
        """Test ASRRuntime with default config."""
        runtime = ASRRuntime()
        assert runtime._config is not None
        assert isinstance(runtime._config, ASRConfig)

    def test_runtime_design_title_with_design_md(self, temp_project_dir):
        """Test _design_title extracts title from DESIGN.md."""
        runtime = ASRRuntime()
        title = runtime._design_title(temp_project_dir)
        assert "Design" in title

    def test_runtime_design_title_no_design_md(self, temp_project_dir):
        """Test _design_title without DESIGN.md returns default."""
        for md_file in temp_project_dir.glob("*.md"):
            md_file.unlink()
        runtime = ASRRuntime()
        title = runtime._design_title(temp_project_dir)
        assert "Build system per design document" in title

    @pytest.mark.asyncio
    async def test_runtime_run_default_spec(self, minimal_config, temp_project_dir):
        """Test ASRRuntime.run with default spec (from DESIGN.md)."""
        runtime = ASRRuntime(minimal_config)

        with patch.object(runtime, '_execute', return_value=ConvergenceResult(
            state=ConvergenceState.CONVERGED,
            iterations=1
        )) as mock_execute:
            result = await runtime.run(temp_project_dir, None)
            assert mock_execute.called
            spec_arg = mock_execute.call_args[0][1]
            assert isinstance(spec_arg, Specification)

    @pytest.mark.asyncio
    async def test_runtime_run_with_spec_file(self, minimal_config, spec_path, temp_project_dir):
        """Test ASRRuntime.run with spec file."""
        runtime = ASRRuntime(minimal_config)

        with patch.object(runtime, '_execute', return_value=ConvergenceResult(
            state=ConvergenceState.CONVERGED,
            iterations=1
        )) as mock_execute:
            result = await runtime.run(temp_project_dir, spec_path)
            assert mock_execute.called
            spec_arg = mock_execute.call_args[0][1]
            assert isinstance(spec_arg, Specification)

    @pytest.mark.asyncio
    async def test_runtime_run_decoupled_mode(self, minimal_config, temp_project_dir):
        """Test ASRRuntime.run with decoupled mode."""
        runtime = ASRRuntime(minimal_config)

        with patch.object(runtime, '_execute', return_value=ConvergenceResult(
            state=ConvergenceState.CONVERGED,
            iterations=1
        )) as mock_execute:
            result = await runtime.run(temp_project_dir, None, use_decoupled=True)
            assert mock_execute.called
            use_decoupled_arg = mock_execute.call_args[0][2]
            assert use_decoupled_arg is True

    @pytest.mark.asyncio
    async def test_runtime_run_with_progress_callback(self, minimal_config, temp_project_dir):
        """Test ASRRuntime.run with progress callback."""
        runtime = ASRRuntime(minimal_config)
        callback_mock = MagicMock()

        with patch.object(runtime, '_execute', return_value=ConvergenceResult(
            state=ConvergenceState.CONVERGED,
            iterations=1
        )) as mock_execute:
            result = await runtime.run(temp_project_dir, None, progress_callback=callback_mock)
            callback_arg = mock_execute.call_args[1].get('progress_callback')
            assert callback_arg == callback_mock

    @pytest.mark.asyncio
    async def test_runtime_create_builder_with_config(self, temp_project_dir):
        """Test _create_builder with builder config."""
        config = ASRConfig(agents=[
            AgentConfig(role="builder", model=ModelConfig(model="gpt-4o"))
        ])
        runtime = ASRRuntime(config)

        builder = runtime._create_builder(temp_project_dir)
        assert builder is not None
        assert builder.name.value == "builder"

    @pytest.mark.asyncio
    async def test_runtime_create_builder_without_config(self, temp_project_dir):
        """Test _create_builder without builder config."""
        config = ASRConfig()
        runtime = ASRRuntime(config)

        builder = runtime._create_builder(temp_project_dir)
        assert builder is None

    @pytest.mark.asyncio
    async def test_runtime_create_tester_with_config(self, temp_project_dir):
        """Test _create_tester with tester config."""
        config = ASRConfig(agents=[
            AgentConfig(role="tester", model=ModelConfig(model="gpt-4o"))
        ])
        runtime = ASRRuntime(config)

        tester = runtime._create_tester(temp_project_dir)
        assert tester is not None
        assert tester.name.value == "tester"

    @pytest.mark.asyncio
    async def test_runtime_create_tester_without_config(self, temp_project_dir):
        """Test _create_tester without tester config."""
        config = ASRConfig()
        runtime = ASRRuntime(config)

        tester = runtime._create_tester(temp_project_dir)
        assert tester is None

    @pytest.mark.asyncio
    async def test_runtime_create_analyzer_with_config(self, temp_project_dir):
        """Test _create_analyzer with analyzer config."""
        config = ASRConfig(agents=[
            AgentConfig(role="analyzer", model=ModelConfig(model="gpt-4o"))
        ])
        runtime = ASRRuntime(config)

        analyzer = runtime._create_analyzer(temp_project_dir)
        assert analyzer is not None
        assert analyzer.name.value == "analyzer"

    @pytest.mark.asyncio
    async def test_runtime_create_analyzer_without_config(self, temp_project_dir):
        """Test _create_analyzer without analyzer config."""
        config = ASRConfig()
        runtime = ASRRuntime(config)

        analyzer = runtime._create_analyzer(temp_project_dir)
        assert analyzer is None

    @pytest.mark.asyncio
    async def test_runtime_agent_model(self, minimal_config):
        """Test _agent_model method."""
        runtime = ASRRuntime(minimal_config)
        model = runtime._agent_model()
        assert model is not None
        assert isinstance(model, ModelConfig)

    @pytest.mark.asyncio
    async def test_runtime_agent_model_with_agents(self, temp_project_dir):
        """Test _agent_model with configured agents."""
        config = ASRConfig(agents=[
            AgentConfig(role="builder", model=ModelConfig(model="custom-model"))
        ])
        runtime = ASRRuntime(config)
        model = runtime._agent_model()
        assert model.model == "custom-model"

    def test_runtime_config_accessor(self, minimal_config):
        """Test runtime config property."""
        runtime = ASRRuntime(minimal_config)
        assert runtime._config == minimal_config

    @pytest.mark.asyncio
    async def test_runtime_run_dag_mode(self, minimal_config, spec_path, temp_project_dir):
        """Test ASRRuntime.run_dag method."""
        runtime = ASRRuntime(minimal_config)

        with patch('asr.runtime.TaskDecomposer') as mock_decomposer:
            mock_dag = MagicMock()
            mock_decomposer.return_value.decompose = AsyncMock(return_value=mock_dag)
            mock_decomposer.return_value.decompose.return_value.total_nodes = 1
            mock_decomposer.return_value.decompose.return_value.converged = 1
            mock_decomposer.return_value.decompose.return_value.stuck = 0
            mock_decomposer.return_value.decompose.return_value.skipped = 0
            mock_decomposer.return_value.decompose.return_value.total_iterations = 1
            mock_decomposer.return_value.decompose.return_value.node_results = {}
            mock_dag.total_nodes = 1
            mock_dag.converged = 1
            mock_dag.stuck = 0
            mock_dag.skipped = 0
            mock_dag.total_iterations = 1
            mock_dag.node_results = {}

            result = await runtime.run_dag(temp_project_dir, spec_path)
            assert result.total_nodes == 1
            assert result.converged == 1

    @pytest.mark.asyncio
    async def test_runtime_run_dag_with_mode(self, minimal_config, spec_path, temp_project_dir):
        """Test ASRRuntime.run_dag with mode parameter."""
        runtime = ASRRuntime(minimal_config)

        with patch('asr.runtime.TaskDecomposer') as mock_decomposer:
            mock_dag = MagicMock()
            mock_decomposer.return_value.decompose = AsyncMock(return_value=mock_dag)
            mock_decomposer.return_value.decompose.return_value.total_nodes = 1
            mock_decomposer.return_value.decompose.return_value.converged = 1
            mock_decomposer.return_value.decompose.return_value.stuck = 0
            mock_decomposer.return_value.decompose.return_value.skipped = 0
            mock_decomposer.return_value.decompose.return_value.total_iterations = 1
            mock_decomposer.return_value.decompose.return_value.node_results = {}
            mock_dag.total_nodes = 1
            mock_dag.converged = 1
            mock_dag.stuck = 0
            mock_dag.skipped = 0
            mock_dag.total_iterations = 1
            mock_dag.node_results = {}

            result = await runtime.run_dag(temp_project_dir, spec_path, mode="features")
            assert result.total_nodes == 1
            assert result.converged == 1

    @pytest.mark.asyncio
    async def test_runtime_convergence_config_validation(self, temp_project_dir):
        """Test runtime with invalid convergence config."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ASRConfig(convergence=ConvergenceConfig(max_iterations=0))

    @pytest.mark.asyncio
    async def test_runtime_runtime_config_paths(self, temp_project_dir):
        """Test runtime with custom runtime config paths."""
        config = ASRConfig(
            runtime=type('RuntimeConfig', (), {
                'event_dir': '/custom/events',
                'inbox_dir': '/custom/inbox',
                'patch_dir': '/custom/patches',
                'state_dir': '/custom/state'
            })()
        )
        runtime = ASRRuntime(config, temp_project_dir)
        assert runtime._event_store is not None
