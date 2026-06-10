"""Tests for ASR configuration models."""

import pytest
from pydantic import ValidationError

from asr.config.models import ModelConfig, AgentConfig, ConvergenceConfig, RuntimeConfig, ASRConfig


def test_model_config_defaults():
    """Test ModelConfig with default values."""
    config = ModelConfig(model="gpt-4o")
    assert config.model == "gpt-4o"
    assert config.temperature == 0.0
    assert config.max_tokens == 4096
    assert config.api_key is None
    assert config.api_base is None
    assert config.timeout == 60
    assert config.num_retries == 2


def test_model_config_validation():
    """Test ModelConfig field validation."""
    # Valid temperature range
    config = ModelConfig(model="gpt-4o", temperature=1.5, max_tokens=8192)
    assert config.temperature == 1.5
    assert config.max_tokens == 8192

    # Invalid temperature (too high)
    with pytest.raises(ValidationError):
        ModelConfig(model="gpt-4o", temperature=3.0)

    # Invalid temperature (negative)
    with pytest.raises(ValidationError):
        ModelConfig(model="gpt-4o", temperature=-0.1)

    # Invalid max_tokens (too high)
    with pytest.raises(ValidationError):
        ModelConfig(model="gpt-4o", max_tokens=300000)


def test_model_config_with_api_key():
    """Test ModelConfig with API configuration."""
    config = ModelConfig(
        model="gpt-4o",
        api_key="sk-test-key",
        api_base="https://api.openai.com/v1"
    )
    assert config.api_key == "sk-test-key"
    assert config.api_base == "https://api.openai.com/v1"


def test_agent_config_defaults():
    """Test AgentConfig with default values."""
    config = AgentConfig(role="builder")
    assert config.role == "builder"
    assert config.model.model == "openai/gpt-4o"
    assert config.system_prompt == ""
    assert config.max_context_messages == 20


def test_agent_config_all_roles():
    """Test AgentConfig with all valid roles."""
    roles = ["builder", "tester", "analyzer", "security", "performance", "architecture"]
    for role in roles:
        config = AgentConfig(role=role)
        assert config.role == role


def test_agent_config_invalid_role():
    """Test AgentConfig with invalid role."""
    with pytest.raises(ValidationError):
        AgentConfig(role="invalid_role")


def test_agent_config_custom_model():
    """Test AgentConfig with custom model configuration."""
    config = AgentConfig(
        role="builder",
        model=ModelConfig(model="claude-3-opus", temperature=0.7)
    )
    assert config.model.model == "claude-3-opus"
    assert config.model.temperature == 0.7


def test_convergence_config_defaults():
    """Test ConvergenceConfig with default values."""
    config = ConvergenceConfig()
    assert config.max_iterations == 10
    assert config.stable_diff_threshold == 2
    assert config.patch_oscillation_threshold == 3
    assert config.test_timeout == 120


def test_convergence_config_custom_values():
    """Test ConvergenceConfig with custom values."""
    config = ConvergenceConfig(
        max_iterations=20,
        stable_diff_threshold=3,
        patch_oscillation_threshold=5,
        test_timeout=180
    )
    assert config.max_iterations == 20
    assert config.stable_diff_threshold == 3
    assert config.patch_oscillation_threshold == 5
    assert config.test_timeout == 180


def test_convergence_config_validation():
    """Test ConvergenceConfig field validation."""
    # Valid max_iterations
    config = ConvergenceConfig(max_iterations=1)
    assert config.max_iterations == 1

    # Invalid max_iterations (zero)
    with pytest.raises(ValidationError):
        ConvergenceConfig(max_iterations=0)


def test_runtime_config_defaults():
    """Test RuntimeConfig with default values."""
    config = RuntimeConfig()
    assert config.event_dir == ".runtime/events"
    assert config.inbox_dir == ".runtime/inbox"
    assert config.patch_dir == ".runtime/patches"
    assert config.state_dir == ".runtime/state"


def test_runtime_config_custom_paths():
    """Test RuntimeConfig with custom paths."""
    config = RuntimeConfig(
        event_dir="/tmp/events",
        inbox_dir="/tmp/inbox",
        patch_dir="/tmp/patches",
        state_dir="/tmp/state"
    )
    assert config.event_dir == "/tmp/events"
    assert config.inbox_dir == "/tmp/inbox"
    assert config.patch_dir == "/tmp/patches"
    assert config.state_dir == "/tmp/state"


def test_asr_config_defaults():
    """Test ASRConfig with default values."""
    config = ASRConfig()
    assert config.default_model == "openai/gpt-4o"
    assert config.agents == []
    assert isinstance(config.convergence, ConvergenceConfig)
    assert isinstance(config.runtime, RuntimeConfig)


def test_asr_config_with_agents():
    """Test ASRConfig with agents."""
    builder_cfg = AgentConfig(role="builder")
    tester_cfg = AgentConfig(role="tester")
    config = ASRConfig(agents=[builder_cfg, tester_cfg])

    assert len(config.agents) == 2
    assert config.agents[0].role == "builder"
    assert config.agents[1].role == "tester"


def test_asr_config_get_agent():
    """Test ASRConfig.get_agent method."""
    builder_cfg = AgentConfig(role="builder")
    tester_cfg = AgentConfig(role="tester")
    config = ASRConfig(agents=[builder_cfg, tester_cfg])

    # Get existing agent
    builder = config.get_agent("builder")
    assert builder is not None
    assert builder.role == "builder"

    tester = config.get_agent("tester")
    assert tester is not None
    assert tester.role == "tester"

    # Get non-existent agent
    analyzer = config.get_agent("analyzer")
    assert analyzer is None


def test_asr_config_get_agent_from_empty():
    """Test ASRConfig.get_agent with no agents."""
    config = ASRConfig()
    assert config.get_agent("builder") is None
    assert config.get_agent("tester") is None


def test_asr_config_serialization():
    """Test ASRConfig serialization."""
    config = ASRConfig(
        default_model="claude-3-opus",
        convergence=ConvergenceConfig(max_iterations=15)
    )
    data = config.model_dump()
    assert data["default_model"] == "claude-3-opus"
    assert data["convergence"]["max_iterations"] == 15

    # Deserialize back
    config2 = ASRConfig(**data)
    assert config2.default_model == "claude-3-opus"
    assert config2.convergence.max_iterations == 15
