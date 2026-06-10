from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    model: str
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=200000)
    api_key: str | None = None
    api_base: str | None = None
    timeout: int = 60
    num_retries: int = 2


class AgentConfig(BaseModel):
    role: Literal["builder", "tester", "analyzer", "security", "performance", "architecture"]
    model: ModelConfig = Field(default_factory=lambda: ModelConfig(model="openai/gpt-4o"))
    system_prompt: str = ""
    max_context_messages: int = 20


class ConvergenceConfig(BaseModel):
    max_iterations: int = Field(default=10, ge=1)
    stable_diff_threshold: int = 2
    patch_oscillation_threshold: int = 3
    repair_timeout: int = 24400
    test_timeout: int = 24400
    analyze_timeout: int = 24400


class RuntimeConfig(BaseModel):
    event_dir: str = ".runtime/events"
    inbox_dir: str = ".runtime/inbox"
    patch_dir: str = ".runtime/patches"
    diff_dir: str = ".runtime/diffs"
    state_dir: str = ".runtime/state"
    task_dir: str = ".runtime/tasks"
    log_dir: str = ".runtime/logs"


class ASRConfig(BaseModel):
    default_model: str = "openai/gpt-4o"
    agents: list[AgentConfig] = Field(default_factory=list)
    convergence: ConvergenceConfig = Field(default_factory=ConvergenceConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    def get_agent(self, role: str) -> AgentConfig | None:
        for agent in self.agents:
            if agent.role == role:
                return agent
        return None
