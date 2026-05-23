"""
OpenCode CLI backend — all ASR agents delegate to `opencode run`.
BuilderAgent uses --continue for session memory.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

OPENCODE_MODEL = os.environ.get("ASR_OPENCODE_MODEL", "qwen/qwen3-next-80b-a3b-instruct")
OPENCODE_TIMEOUT = int(os.environ.get("ASR_OPENCODE_TIMEOUT", "120"))


def _parse_session_id(stdout: str) -> str | None:
    for line in stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            sid = data.get("sessionID")
            if sid:
                return sid
        except json.JSONDecodeError:
            pass
    return None


def _parse_tokens(stdout: str) -> tuple[int, int, int]:
    total = prompt = completion = 0
    for line in stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("type") == "step_finish":
            t = data.get("part", {}).get("tokens", {})
            total += t.get("total", 0)
            prompt += t.get("input", 0)
            completion += t.get("output", 0)
    return prompt, completion, total


def _parse_text(stdout: str) -> str:
    parts = []
    for line in stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("type") == "text":
            parts.append(data.get("part", {}).get("text", ""))
    return "".join(parts)


def _run_opencode(prompt: str, project_dir: Path, session_id: str | None = None,
                  timeout: int = OPENCODE_TIMEOUT) -> tuple[str, str | None, int, int, int]:
    cmd = [
        "opencode", "run",
        "--model", OPENCODE_MODEL,
        "--dangerously-skip-permissions",
        "--format", "json",
        "--dir", str(project_dir),
    ]
    if session_id:
        cmd.extend(["--session", session_id, "--continue"])
    cmd.append(prompt)

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        env={**os.environ, "CI": "true", "GIT_TERMINAL_PROMPT": "0"},
    )
    new_session_id = _parse_session_id(result.stdout)
    pt, ct, tt = _parse_tokens(result.stdout)
    text = _parse_text(result.stdout)
    return text, new_session_id or session_id, pt, ct, tt


async def opencode_completion(prompt: str, project_dir: Path,
                              timeout: int = OPENCODE_TIMEOUT) -> tuple[str, int, int, int]:
    text, _, pt, ct, tt = await asyncio.to_thread(_run_opencode, prompt, project_dir, None, timeout)
    return text, pt, ct, tt


def opencode_diff(prompt: str, project_dir: Path, session_id: str | None = None,
                  timeout: int = OPENCODE_TIMEOUT) -> tuple[str, str | None, int, int, int]:
    text, new_sid, pt, ct, tt = _run_opencode(prompt, project_dir, session_id, timeout)

    subprocess.run(["git", "add", "-A"], cwd=str(project_dir),
                   capture_output=True, timeout=10)
    diff_result = subprocess.run(
        ["git", "diff", "--cached", "HEAD"],
        cwd=str(project_dir), capture_output=True, text=True, timeout=30,
    )
    diff_text = diff_result.stdout.strip()

    if diff_text:
        subprocess.run(["git", "commit", "-m", "opencode_changes"],
                       cwd=str(project_dir), capture_output=True, timeout=10)

    return diff_text or "no changes", new_sid, pt, ct, tt


async def opencode_diff_async(prompt: str, project_dir: Path, session_id: str | None = None,
                              timeout: int = OPENCODE_TIMEOUT) -> tuple[str, str | None, int, int, int]:
    return await asyncio.to_thread(opencode_diff, prompt, project_dir, session_id, timeout)
