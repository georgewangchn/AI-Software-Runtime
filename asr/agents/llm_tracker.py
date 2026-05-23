"""
Shared LLM token usage tracker.
Writes JSON lines to .runtime/logs/llm.jsonl for benchmark consumption.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def log_token_usage(
    agent: str,
    model: str,
    usage: Any,
    log_dir: str | Path = ".runtime/logs",
) -> None:
    """Log token usage from a litellm response to llm.jsonl."""
    try:
        if hasattr(usage, "to_dict"):
            usage = usage.to_dict()
        if not isinstance(usage, dict):
            return

        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        llm_log = log_path / "llm.jsonl"

        entry = {
            "agent": agent,
            "model": model,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "timestamp": time.time(),
        }
        with open(llm_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # never crash on logging
