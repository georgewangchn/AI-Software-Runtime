from __future__ import annotations

import os
from pathlib import Path

import yaml

from asr.config.models import (
    ASRConfig,
    ModelConfig,
    AgentConfig,
    ConvergenceConfig,
    RuntimeConfig,
)


def _load_dotenv() -> dict[str, str]:
    env_vars: dict[str, str] = {}
    for env_path in [
        Path(".env"),
        Path.cwd() / ".env",
        Path(__file__).parent.parent.parent / ".env",
    ]:
        if env_path.exists():
            for line in env_path.read_text().split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env_vars[key.strip()] = val.strip()
    return env_vars


def _resolve_env_vars(value: str) -> str:
    if value.startswith("os.environ/"):
        var_name = value[len("os.environ/"):]
        return os.environ.get(var_name, value)
    return value


def load_config(path: str | Path) -> ASRConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)

    if "agents" in raw:
        for agent in raw["agents"]:
            if "model" in agent:
                model = agent["model"]
                if "api_key" in model:
                    model["api_key"] = _resolve_env_vars(model["api_key"])
                if "api_base" in model:
                    model["api_base"] = _resolve_env_vars(model["api_base"])

    return ASRConfig(**raw)


def create_default_config() -> ASRConfig:
    dotenv = _load_dotenv()

    model_name = dotenv.get("FEASIBILITY_LLM_MODEL", "openai/glm-4.7-fp8")
    if "/" not in model_name:
        model_name = f"openai/{model_name}"

    api_base = dotenv.get("FEASIBILITY_LLM_API_BASE", "http://192.168.1.12:8000/v1")
    api_key = dotenv.get("FEASIBILITY_LLM_API_KEY", "sk-123456")

    glm_model = ModelConfig(
        model=model_name,
        api_base=api_base,
        api_key=api_key,
        temperature=0.0,
        max_tokens=8192,
        timeout=300,
        num_retries=2,
    )

    return ASRConfig(
        default_model=model_name,
        agents=[
            AgentConfig(
                role="builder",
                model=glm_model,
                system_prompt=(
                    "You are a BuilderAgent in an AI Software Convergence Runtime. "
                    "Your job: generate code from specifications and produce unified diffs to fix test failures. "
                    "Output format: unified diff wrapped in ```diff fences. "
                    "Rules: only modify files that need changes (local repair, not full rewrite). "
                    "Include context lines in diffs for accurate patching. "
                    "Address ALL failures listed in the test report. "
                    "Do NOT write or modify test files."
                ),
                max_context_messages=20,
            ),
            AgentConfig(
                role="analyzer",
                model=glm_model,
                system_prompt=(
                    "You are an AnalyzerAgent in an AI Software Convergence Runtime. "
                    "Your job: compare implementation against specification and identify semantic gaps. "
                    "You do NOT check test results — TesterAgent handles that. "
                    "Focus on: missing features, logic errors, constraint violations. "
                    "Output format: YAML with missing_features, logic_issues, constraint_violations lists."
                ),
                max_context_messages=10,
            ),
            AgentConfig(
                role="tester",
                model=ModelConfig(model="none"),
            ),
        ],
        convergence=ConvergenceConfig(
            max_iterations=5,
            stable_diff_threshold=2,
            patch_oscillation_threshold=3,
            test_timeout=120,
        ),
        runtime=RuntimeConfig(),
    )
