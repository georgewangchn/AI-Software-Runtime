from __future__ import annotations

import time
from pathlib import Path


class ASRLogger:
    def __init__(self, log_dir: str = ".runtime/logs"):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, level: str, message: str, agent: str = "") -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] [{level:5s}] [{agent:12s}] {message}"
        log_path = self._log_dir / "asr.log"
        with open(log_path, "a") as f:
            f.write(line + "\n")

    def log_convergence(self, iteration: int, errors: int, phase: str, detail: str) -> None:
        ts = time.strftime("%H:%M:%S")
        elapsed = time.time() - getattr(self, '_start', time.time())
        if not hasattr(self, '_start'):
            self._start = time.time()
        line = f"[{ts}] [{elapsed:5.1f}s] [CONV ] [controller  ] iter={iteration:>3} errors={errors} phase={phase:<12} {detail}"
        log_path = self._log_dir / "asr.log"
        with open(log_path, "a") as f:
            f.write(line + "\n")
