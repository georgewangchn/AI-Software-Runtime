"""
OpenCode CLI backend — all ASR agents delegate to `opencode run`.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

OPENCODE_TIMEOUT = int(os.environ.get("ASR_OPENCODE_TIMEOUT", "24400"))
VERBOSE = os.environ.get("ASR_VERBOSE", "") != ""
# asyncio create_subprocess_exec default stream buffer is 64KB.
# opencode --format json emits long lines (tool results with embedded file contents).
# 10MB default prevents "Separator is found, but chunk is longer than limit" errors.
STREAM_LIMIT = int(os.environ.get("ASR_STREAM_LIMIT", str(10 * 1024 * 1024)))


def _print_progress(data: dict, label: str) -> None:
    if not VERBOSE:
        return
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    msg_type = data.get("type", "")
    if msg_type == "step_start":
        name = data.get("part", {}).get("name", "")
        if name:
            print(f"  {ts} [{label}] {name}", file=sys.stderr, flush=True)
    elif msg_type == "text":
        text = data.get("part", {}).get("text", "") or data.get("content", "")
        if text:
            preview = text.strip().replace("\n", " ")[:200]
            print(f"  {ts} [{label}] {preview}", file=sys.stderr, flush=True)


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
                        session_id: str | None = None,
                        label: str = "") -> tuple[str, str | None, int, int, int]:
    cmd = _build_opencode_cmd(project_dir, session_id)
    cmd.append(prompt)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.DEVNULL,
        limit=STREAM_LIMIT,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    assert proc.stdout is not None and proc.stderr is not None
    try:
        stdout_lines: list[str] = []
        while True:
            line_bytes = await proc.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode()
            stdout_lines.append(line)
            try:
                _print_progress(json.loads(line.strip()), label)
            except json.JSONDecodeError:
                pass
        stderr_bytes = await proc.stderr.read()
        await proc.wait()
    except asyncio.CancelledError:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        raise
    except Exception:
        # readline may raise ValueError if a single JSON line exceeds STREAM_LIMIT.
        # Ensure the subprocess is cleaned up before re-raising.
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        raise

    stdout_text = "".join(stdout_lines)
    stderr_text = stderr_bytes.decode() if stderr_bytes else ""

    if proc.returncode and proc.returncode != -15:
        print(f"[opencode] exit={proc.returncode} err={stderr_text[:200]}", file=sys.stderr)

    new_session_id = _parse_session_id(stdout_text)
    pt, ct, tt = _parse_tokens(stdout_text)
    text = _parse_text(stdout_text)
    return text, new_session_id or session_id, pt, ct, tt


async def opencode_completion(prompt: str, project_dir: Path,
                              label: str = "") -> tuple[str, int, int, int]:
    text, _, pt, ct, tt = await _run_opencode(prompt, project_dir, label=label)
    return text, pt, ct, tt


async def opencode_run(prompt: str, project_dir: Path,
                       session_id: str | None = None,
                       label: str = "") -> tuple[str | None, int, int, int]:
    _, new_sid, pt, ct, tt = await _run_opencode(prompt, project_dir, session_id, label=label)
    return new_sid, pt, ct, tt
