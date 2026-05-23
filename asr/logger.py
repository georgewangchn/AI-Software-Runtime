from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path


class ASRLogger:
    def __init__(self, log_dir: str | Path = ".runtime/logs"):
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._main = self._dir / "asr.log"
        self._llm = self._dir / "llm.log"
        self._agents: dict[str, Path] = {}
        self._start_time = time.time()

    def log(self, level: str, message: str, agent: str = "system") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        elapsed = f"{time.time() - self._start_time:.1f}s"
        line = f"[{ts}] [{elapsed:>6}] [{level:<5}] [{agent:<12}] {message}\n"
        self._main.write_text(self._main.read_text() + line if self._main.exists() else line)

    def log_event(self, event_type: str, details: str) -> None:
        self.log("EVENT", f"{event_type}: {details}", agent="controller")

    def log_agent(self, agent: str, action: str, detail: str = "") -> None:
        self.log("AGENT", f"{action} {detail}", agent=agent)
        path = self._dir / f"agent_{agent}.log"
        ts = datetime.now().strftime("%H:%M:%S")
        path.write_text(path.read_text() + f"[{ts}] {action}: {detail}\n" if path.exists() else f"[{ts}] {action}: {detail}\n")

    def log_llm(self, agent: str, model: str, prompt_len: int, response_len: int, content_preview: str = "") -> None:
        self.log("LLM", f"→ {model} (prompt={prompt_len} chars, response={response_len} chars)", agent=agent)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"\n{'='*60}\n"
            f"[{ts}] Agent: {agent} | Model: {model}\n"
            f"Prompt: {prompt_len} chars | Response: {response_len} chars\n"
            f"Preview: {content_preview[:200]}\n"
            f"{'='*60}\n"
        )
        self._llm.write_text(self._llm.read_text() + entry if self._llm.exists() else entry)

    def log_test(self, total: int, passed: int, failed: int, errors: int, duration: float) -> None:
        self.log("TEST", f"total={total} passed={passed} failed={failed} errors={errors} duration={duration:.2f}s", agent="tester")

    def log_convergence(self, iteration: int, errors: int, phase: str, detail: str = "") -> None:
        icon = "🔧" if phase == "REPAIRING" else "🧪" if phase == "TESTING" else "🔍" if phase == "ANALYZING" else "  "
        self.log("CONV", f"iter={iteration:>3} errors={errors} phase={phase:<12} {icon} {detail}", agent="controller")

    def log_result(self, state: str, iterations: int, reason: str = "") -> None:
        elapsed = time.time() - self._start_time
        self.log("DONE", f"state={state} iterations={iterations} elapsed={elapsed:.1f}s {reason}", agent="controller")
