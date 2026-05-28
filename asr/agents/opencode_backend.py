"""
OpenCode CLI backend — all ASR agents delegate to `opencode run`.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

OPENCODE_TIMEOUT = int(os.environ.get("ASR_OPENCODE_TIMEOUT", "14400"))


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
        part = data.get("part", {})
        if isinstance(part, dict):
            text = part.get("text", "") or part.get("content", "")
            if text:
                parts.append(text)
                continue
        if isinstance(data.get("message"), dict):
            text = data["message"].get("content", "")
            if text:
                parts.append(text)
    return "".join(parts)


def _build_opencode_cmd(project_dir: Path, session_id: str | None = None) -> list[str]:
    cmd = [
        "opencode", "run",
        "--dangerously-skip-permissions",
        "--format", "json",
        "--dir", str(project_dir),
    ]
    if session_id:
        cmd.extend(["--session", session_id, "--continue"])
    return cmd


async def _run_opencode(prompt: str, project_dir: Path,
                        session_id: str | None = None) -> tuple[str, str | None, int, int, int]:
    cmd = _build_opencode_cmd(project_dir, session_id)
    cmd.append(prompt)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.DEVNULL,
        env={**os.environ, "CI": "true", "GIT_TERMINAL_PROMPT": "0"},
    )
    try:
        stdout_bytes, stderr_bytes = await proc.communicate()
    except asyncio.CancelledError:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        raise

    stdout_text = stdout_bytes.decode() if stdout_bytes else ""
    stderr_text = stderr_bytes.decode() if stderr_bytes else ""

    if proc.returncode and proc.returncode != -15:
        import sys
        print(f"[opencode] exit={proc.returncode} err={stderr_text[:200]}", file=sys.stderr)

    new_session_id = _parse_session_id(stdout_text)
    pt, ct, tt = _parse_tokens(stdout_text)
    text = _parse_text(stdout_text)
    return text, new_session_id or session_id, pt, ct, tt


async def opencode_completion(prompt: str, project_dir: Path) -> tuple[str, int, int, int]:
    text, _, pt, ct, tt = await _run_opencode(prompt, project_dir)
    return text, pt, ct, tt


async def opencode_run(prompt: str, project_dir: Path,
                       session_id: str | None = None) -> tuple[str | None, int, int, int]:
    _, new_sid, pt, ct, tt = await _run_opencode(prompt, project_dir, session_id)
    return new_sid, pt, ct, tt
