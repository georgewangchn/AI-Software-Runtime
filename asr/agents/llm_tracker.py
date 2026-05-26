"""
Shared LLM token usage tracker.
Writes JSON lines to .runtime/logs/llm.jsonl for benchmark consumption.
Also maintains in-memory counters for real-time progress display.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_token_store: dict[str, dict[str, int]] = {}


def _ensure_agent(agent: str) -> dict[str, int]:
    if agent not in _token_store:
        _token_store[agent] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0}
    return _token_store[agent]


def log_token_usage(
    agent: str,
    model: str,
    usage: Any,
    log_dir: str | Path = ".runtime/logs",
) -> None:
    """Log token usage from a litellm response to llm.jsonl and in-memory store."""
    try:
        if hasattr(usage, "to_dict"):
            usage = usage.to_dict()
        if not isinstance(usage, dict):
            return

        pt = usage.get("prompt_tokens", 0)
        ct = usage.get("completion_tokens", 0)
        tt = usage.get("total_tokens", 0)

        st = _ensure_agent(agent)
        st["prompt_tokens"] += pt
        st["completion_tokens"] += ct
        st["total_tokens"] += tt
        st["calls"] += 1

        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        llm_log = log_path / "llm.jsonl"

        entry = {
            "agent": agent,
            "model": model,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": tt,
            "timestamp": time.time(),
        }
        with open(llm_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # never crash on logging


def get_agent_tokens(agent: str) -> dict[str, int]:
    """Get cumulative token counts for an agent."""
    return dict(_token_store.get(agent, {}))


def get_all_tokens() -> dict[str, dict[str, int]]:
    """Get cumulative token counts for all agents."""
    return dict(_token_store)


def reset_tokens() -> None:
    """Reset in-memory token counters (does not touch llm.jsonl)."""
    _token_store.clear()
