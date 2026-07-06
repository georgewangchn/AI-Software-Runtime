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
    # 显式控制指标权重（error_score 计算）
    w_test_failed: float = 1.0
    w_test_error: float = 2.0
    w_missing_feature: float = 1.5
    w_logic_issue: float = 1.0
    w_constraint_violation: float = 0.8
    w_high_severity: float = 2.0
    w_patch_regression: float = 1.0
    # Patch 限幅（Phase 3）
    max_files_per_patch: int = 10
    max_lines_per_patch: int = 200
    max_deleted_lines_per_patch: int = 50
    allow_large_patch_in_initial: bool = True
    # 硬拒绝：patch 超标时要求 Builder 重做（而不仅仅是 prompt 提示）
    hard_reject_oversized_patch: bool = True
    # Circuit breaker：连续 N 轮 test_pass_rate 无改善则停止
    circuit_breaker_stagnant_iters: int = 6


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
