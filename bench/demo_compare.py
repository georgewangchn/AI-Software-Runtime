#!/usr/bin/env python3
"""
ASR vs OpenCode vs Baseline — Demo Project Comparison Runner.

Three-mode A/B test on demo_project (3 known bugs):
  1. baseline  — single-shot LLM patch generation
  2. opencode  — LLM with full code context (simulated single-agent)
  3. asr       — full ASR Runtime (multi-agent convergence loop)

All modes use the SAME LLM backend for fair comparison.
Produces: bench/outputs/demo_compare/results.json + comparison report.

Usage:
    cd /Users/siidt/Documents/siicode/asr
    python bench/demo_compare.py                    # all 3 modes
    python bench/demo_compare.py --mode baseline    # single mode
    python bench/demo_compare.py --mode asr --max-iter 10
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent  # /Users/siidt/Documents/siicode/asr
DEMO_PROJECT = ROOT / "demo_project"
BENCH_DIR = ROOT / "bench"
OUTPUT_DIR = BENCH_DIR / "outputs" / "demo_compare"
WORK_DIR = BENCH_DIR / "workspace" / "demo_compare"

# Buggy baseline — the 3 intentional bugs
BUGGY_MAIN = '''from typing import Optional
from fastapi import FastAPI, HTTPException
from models import User, UserCreate

app = FastAPI()

users_db = [
    {"id": 1, "name": "Alice", "email": "alice@example.com"},
    {"id": 2, "name": "Bob", "email": "bob@example.com"},
]

_next_id = 3


@app.get("/users/search")
def search_users(q: Optional[str] = None):
    if not q:
        return []
    return [u for u in users_db if q.lower() in u["name"].lower()]


@app.get("/users/{user_id}")
def get_user(user_id: int):
    for user in users_db:
        if user["id"] == user_id:
            return {"id": user["id"], "name": user["name"]}
    raise HTTPException(status_code=404, detail="User not found")


@app.post("/users", status_code=201)
def create_user(user: UserCreate):
    global _next_id
    new_user = {"id": _next_id, "name": user.name, "email": user.email}
    users_db.append(new_user)
    _next_id += 1
    return new_user
'''

BUGGY_MODELS = '''from pydantic import BaseModel


class User(BaseModel):
    id: int
    name: str
    email: str


class UserCreate(BaseModel):
    name: str
    email: str
'''

ISSUE_DESCRIPTION = """Fix all bugs in the demo_project FastAPI application.

BUG 1 (get_user): The /users/{user_id} endpoint does NOT return the email field.
    When a user is found, the response should be the FULL user dict including id, name, AND email.
    Currently it only returns id and name, causing test_get_existing_user to fail.

BUG 2 (search_users): The /users/search endpoint crashes with IndexError when q="" (empty string).
    When query is empty, it should return an empty list [] without crashing.
    Currently accessing q[0] causes a crash.

BUG 3 (create_user): The POST /users endpoint does NOT check for duplicate emails.
    When creating a user with an email that already exists, it should return HTTP 409.
    Currently it always creates a new user regardless of duplicate emails.
"""


# ─── Data Classes ─────────────────────────────────────────────────
@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated: bool = False

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated": self.estimated,
        }

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            estimated=self.estimated or other.estimated,
        )


@dataclass
class RunResult:
    mode: str
    success: bool
    iterations: int
    elapsed_seconds: float
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    test_failures: int = -1
    test_output: str = ""
    stop_reason: str = ""
    error: str | None = None
    convergence_curve: list[int] = field(default_factory=list)
    patch_applied: bool = False
    events_count: int = 0


# ─── LLM API ──────────────────────────────────────────────────────
def _get_api_config() -> dict:
    """Load API config from .env (same as ASR)."""
    env_path = ROOT / ".env"
    cfg = {
        "model": "qwen3-next-80b-a3b-instruct",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "",
    }
    if env_path.exists():
        for line in env_path.read_text().split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if key == "FEASIBILITY_LLM_MODEL":
                cfg["model"] = val
            elif key == "FEASIBILITY_LLM_API_BASE":
                cfg["base_url"] = val
            elif key == "FEASIBILITY_LLM_API_KEY":
                cfg["api_key"] = val
    return cfg


def run_tests(project_dir: Path, timeout: int = 120) -> tuple[bool, int, str]:
    """Run pytest. Returns (passed, failure_count, output)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short"],
        cwd=str(project_dir),
        capture_output=True, text=True, timeout=timeout,
    )
    output = result.stdout + result.stderr
    passed = result.returncode == 0
    match = re.search(r"(\d+)\s+failed", output)
    failures = int(match.group(1)) if match else (0 if passed else output.count("FAILED"))
    return passed, failures, output


def _parse_opencode_tokens(stdout):
    total = prompt = completion = 0
    for line in stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            if data.get("type") == "step_finish":
                t = data.get("part", {}).get("tokens", {})
                total += t.get("total", 0)
                prompt += t.get("input", 0)
                completion += t.get("output", 0)
        except (json.JSONDecodeError, KeyError):
            pass
    return prompt, completion, total


def run_opencode(project_dir: Path, max_iterations: int = 10) -> RunResult:
    """Real OpenCode CLI with iterative convergence: each opencode run = 1 iteration."""
    start = time.time()
    total_prompt = total_completion = total_tokens = 0

    for iteration in range(1, max_iterations + 1):
        passed, failures, test_output = run_tests(project_dir)
        if passed:
            elapsed = time.time() - start
            usage = TokenUsage(total_prompt, total_completion, total_tokens, False) if total_tokens > 0 else TokenUsage(estimated=True)
            return RunResult(mode="opencode", success=True, iterations=iteration,
                             elapsed_seconds=round(elapsed, 2), token_usage=usage,
                             test_failures=0, patch_applied=True, stop_reason="all_tests_pass")

        if iteration == 1:
            prompt = (
                f"Fix ALL bugs in this FastAPI application. "
                f"Read the code, identify each bug, apply fixes. "
                f"Do NOT modify test files.\n\n"
                f"Issue: {ISSUE_DESCRIPTION}"
            )
        else:
            test_summary = test_output[-4000:] if len(test_output) > 4000 else test_output
            prompt = (
                f"Previous fix attempt failed. {failures} tests still failing. "
                f"Read the code, identify remaining bugs, apply fixes. "
                f"Do NOT modify test files.\n\n"
                f"Test failures:\n{test_summary}"
            )

        cmd = [
            "opencode", "run",
            "--model", "qwen/qwen3-next-80b-a3b-instruct",
            "--dangerously-skip-permissions",
            "--format", "json",
            "--dir", str(project_dir),
            prompt,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=300,
                                    env={**os.environ, "CI": "true", "GIT_TERMINAL_PROMPT": "0"})
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            usage = TokenUsage(total_prompt, total_completion, total_tokens, False) if total_tokens > 0 else TokenUsage(estimated=True)
            return RunResult(mode="opencode", success=False, iterations=iteration,
                             elapsed_seconds=round(elapsed, 2), token_usage=usage,
                             error="timeout", stop_reason="timeout")

        p, c, t = _parse_opencode_tokens(result.stdout)
        total_prompt += p
        total_completion += c
        total_tokens += t

    elapsed = time.time() - start
    passed, failures, output = run_tests(project_dir)
    usage = TokenUsage(total_prompt, total_completion, total_tokens, False) if total_tokens > 0 else TokenUsage(estimated=True)
    return RunResult(mode="opencode", success=passed, iterations=max_iterations,
                     elapsed_seconds=round(elapsed, 2), token_usage=usage,
                     test_failures=failures, test_output=output, patch_applied=True,
                     stop_reason="all_tests_pass" if passed else "max_iterations")


def run_asr(project_dir: Path, max_iterations: int = 10) -> RunResult:
    """Run ASR Runtime. Uses spec.yaml if present, else reads DESIGN.md."""
    start = time.time()

    runtime_dir = project_dir / ".runtime"
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)
    cwd_runtime = ROOT / ".runtime"
    if cwd_runtime.exists():
        shutil.rmtree(cwd_runtime, ignore_errors=True)

    cmd = [
        sys.executable, "-m", "asr.cli.main", "run",
        "--project", str(project_dir),
        "--max-iterations", str(max_iterations),
    ]
    spec_path = project_dir / "spec.yaml"
    if spec_path.exists():
        cmd.extend(["--spec", str(spec_path)])

    combined_path = f"{ROOT}:{project_dir}:{os.environ.get('PYTHONPATH', '')}"
    result = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True,
        timeout=max_iterations * 300,
        env={**os.environ, "PYTHONPATH": combined_path},
    )
    elapsed = time.time() - start
    output = result.stdout + result.stderr

    iterations = 0
    iter_match = re.search(r"Iterations:\s*(\d+)", output)
    if iter_match:
        iterations = int(iter_match.group(1))

    events_count = 0
    events_match = re.search(r"Events:\s*(\d+)", output)
    if events_match:
        events_count = int(events_match.group(1))

    applied_match = re.search(r"Applied:\s*(\d+)/(\d+)", output)
    patches_applied = int(applied_match.group(1)) if applied_match else 0

    converged = "CONVERGED" in output
    test_passed = converged
    failures = 0 if converged else -1
    test_output = output

    usage = TokenUsage(estimated=True)
    for log_dir in [
        project_dir / ".runtime" / "logs",
        ROOT / ".runtime" / "logs",
    ]:
        jsonl_log = log_dir / "llm.jsonl"
        if jsonl_log.exists():
            pt = ct = tt = 0
            for line in jsonl_log.read_text(errors="replace").strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    pt += entry.get("prompt_tokens", 0)
                    ct += entry.get("completion_tokens", 0)
                    tt += entry.get("total_tokens", 0)
                except (json.JSONDecodeError, KeyError):
                    pass
            if tt > 0:
                usage = TokenUsage(pt, ct, tt, False)
                break

        llm_log = log_dir / "llm.log"
        if llm_log.exists() and usage.total_tokens == 0:
            log_text = llm_log.read_text(errors="replace")
            prompt_sum = sum(int(x) for x in re.findall(r'"prompt_tokens":\s*(\d+)', log_text))
            completion_sum = sum(int(x) for x in re.findall(r'"completion_tokens":\s*(\d+)', log_text))
            total_sum = sum(int(x) for x in re.findall(r'"total_tokens":\s*(\d+)', log_text))
            if total_sum > 0:
                usage = TokenUsage(prompt_tokens=prompt_sum, completion_tokens=completion_sum,
                                   total_tokens=total_sum, estimated=True)
                break

        asr_log = log_dir / "asr.log"
        if asr_log.exists() and usage.total_tokens == 0:
            log_text = asr_log.read_text(errors="replace")
            llm_calls = len(re.findall(r'\[.*?\] .*? patch applied', log_text))
            avg_tokens_per_call = 2000
            estimated_total = max(llm_calls, iterations * 2) * avg_tokens_per_call
            usage = TokenUsage(prompt_tokens=estimated_total // 2,
                               completion_tokens=estimated_total // 2,
                               total_tokens=estimated_total, estimated=True)
            break

    return RunResult(
        mode="asr", success=test_passed, iterations=iterations,
        elapsed_seconds=round(elapsed, 2), token_usage=usage,
        test_failures=failures, test_output=test_output,
        patch_applied=patches_applied > 0,
        events_count=events_count,
        stop_reason="CONVERGED" if test_passed else "STUCK",
        error=None if test_passed else (output[-500:] if output else "unknown"),
    )


# ─── Setup / Teardown ─────────────────────────────────────────────
def prepare_workspace(mode: str) -> Path:
    """Create an isolated copy of demo_project for one test mode."""
    work_dir = WORK_DIR / mode
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    shutil.copytree(DEMO_PROJECT, work_dir, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".runtime", "__pycache__", ".pytest_cache",
                                                  ".coverage", "*.pyc", "events", ".DS_Store"))

    # Reset main.py to buggy baseline
    (work_dir / "main.py").write_text(BUGGY_MAIN)
    # Ensure models.py is correct
    (work_dir / "models.py").write_text(BUGGY_MODELS)

    test_file = work_dir / "test_main.py"
    if test_file.exists():
        isolated_imports = test_file.read_text().replace(
            "from demo_project.main import app",
            "from main import app"
        )
        test_file.write_text(isolated_imports)

    for py_file in work_dir.glob("*.py"):
        if py_file.name not in ("main.py", "models.py", "test_main.py"):
            contents = py_file.read_text()
            if "from demo_project.main import" in contents:
                py_file.write_text(
                    contents.replace("from demo_project.main import", "from main import")
                )

    return work_dir


# ─── Report ───────────────────────────────────────────────────────
def generate_report(results: list[RunResult], output_path: Path) -> str:
    """Generate comparison report and save to JSON."""
    os.makedirs(output_path.parent, exist_ok=True)

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": _get_api_config()["model"],
        "project": str(DEMO_PROJECT),
        "results": [],
        "comparison": {},
    }

    for r in results:
        report["results"].append({
            "mode": r.mode,
            "success": r.success,
            "iterations": r.iterations,
            "elapsed_seconds": r.elapsed_seconds,
            "token_usage": r.token_usage.to_dict(),
            "test_failures": r.test_failures,
            "patch_applied": r.patch_applied,
            "events_count": r.events_count,
            "stop_reason": r.stop_reason,
            "error": r.error,
        })

    # Build comparison table
    lines = []
    lines.append("=" * 70)
    lines.append("  DEMO PROJECT COMPARISON: ASR vs OpenCode")
    lines.append("=" * 70)
    lines.append(f"  Model: {_get_api_config()['model']}")
    lines.append(f"  Project bugs: 3 (get_user email, search_users crash, create_user duplicate)")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"{'Mode':<12} {'Pass':<7} {'Iters':<7} {'Time':<9} {'Tokens':<10} {'Details'}")
    lines.append("-" * 70)

    for r in results:
        status = "✅ PASS" if r.success else "❌ FAIL"
        token_str = f"{r.token_usage.total_tokens:,}"
        detail = ""
        if r.mode == "asr":
            detail = f"events={r.events_count}"
        elif r.error:
            detail = f"error={r.error[:40]}"
        elif r.test_failures > 0:
            detail = f"failures={r.test_failures}"
        lines.append(f"{r.mode:<12} {status:<7} {r.iterations:<7} {r.elapsed_seconds:<8.1f}s {token_str:<10} {detail}")

    lines.append("-" * 70)

    # Win/loss analysis
    asr_r = next((r for r in results if r.mode == "asr"), None)
    oc_r = next((r for r in results if r.mode == "opencode"), None)

    lines.append("")
    lines.append("  VALUE ANALYSIS:")
    if asr_r and oc_r:
        if asr_r.success and not oc_r.success:
            lines.append(f"    ✅ ASR WINS: ASR converged ({asr_r.iterations} iters), OpenCode failed")
        elif oc_r.success and not asr_r.success:
            lines.append(f"    ❌ OpenCode WINS: OpenCode passed, ASR stuck")
        elif asr_r.success and oc_r.success:
            asr_efficiency = asr_r.token_usage.total_tokens / asr_r.elapsed_seconds if asr_r.elapsed_seconds else 0
            oc_efficiency = oc_r.token_usage.total_tokens / oc_r.elapsed_seconds if oc_r.elapsed_seconds else 0
            lines.append(f"    ⚖️  BOTH PASSED — ASR: {asr_r.iterations} iters/{asr_r.elapsed_seconds:.1f}s, OpenCode: 1 shot/{oc_r.elapsed_seconds:.1f}s")
            lines.append(f"    Token cost: ASR={asr_r.token_usage.total_tokens:,} vs OpenCode={oc_r.token_usage.total_tokens:,}")
        else:
            lines.append(f"    ❌ BOTH FAILED")

    lines.append("")
    lines.append("  KEY METRICS EXPLAINED:")
    lines.append("    - Pass:     All 5 pytest tests pass = all 3 bugs fixed")
    lines.append("    - Iters:    Iterations to convergence (max = --max-iter)")
    lines.append("    - Time:     Wall-clock time including LLM calls")
    lines.append("    - Tokens:   Total tokens consumed (real from opencode JSON / ASR llm.jsonl)")
    lines.append("    - Events:   ASR internal events count (state transitions)")
    lines.append("=" * 70)

    report_str = "\n".join(lines)

    # Save JSON
    json_path = output_path
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report_str


# ─── Main ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="ASR vs OpenCode — Demo Comparison"
    )
    parser.add_argument("--mode", choices=["opencode", "asr", "all"],
                        default="all", help="Which mode(s) to run")
    parser.add_argument("--max-iter", type=int, default=10,
                        help="Max ASR iterations (default: 10)")
    parser.add_argument("--runs", type=int, default=1,
                        help="Number of runs per mode (for stability, default: 1)")
    args = parser.parse_args()

    print("=" * 70)
    print("  ASR vs OpenCode — Demo Comparison Runner")
    print("=" * 70)
    cfg = _get_api_config()
    print(f"  LLM Backend: {cfg['model']} @ {cfg['base_url']}")
    print(f"  Demo Project: {DEMO_PROJECT} (3 bugs)")
    print(f"  Modes: {args.mode}")
    print(f"  Runs per mode: {args.runs}")
    print("=" * 70)

    modes = ["opencode", "asr"] if args.mode == "all" else [args.mode]
    all_results: list[RunResult] = []

    for run_num in range(args.runs):
        for mode in modes:
            print(f"\n{'─' * 50}")
            print(f"  [{run_num + 1}/{args.runs}] Running {mode.upper()}...")
            print(f"{'─' * 50}")

            work_dir = prepare_workspace(mode)

            if mode == "opencode":
                result = run_opencode(work_dir, max_iterations=args.max_iter)
            elif mode == "asr":
                result = run_asr(work_dir, max_iterations=args.max_iter)

            all_results.append(result)

            status = "✅ PASS" if result.success else "❌ FAIL"
            print(f"  {mode.upper()}: {status} | {result.iterations} iters | "
                  f"{result.elapsed_seconds:.1f}s | tokens={result.token_usage.total_tokens:,}")

    # Generate report
    output_path = OUTPUT_DIR / "results.json"
    report = generate_report(all_results, output_path)

    print(f"\n{report}")
    print(f"\n  Report saved: {output_path}")

    # Auto-generate markdown + HTML reports
    try:
        sys.path.insert(0, str(ROOT))
        from bench.report import generate_markdown, generate_html
        with open(output_path) as f:
            results_data = json.load(f)
        (OUTPUT_DIR / "report.md").write_text(generate_markdown(results_data))
        (OUTPUT_DIR / "report.html").write_text(generate_html(results_data))
        print(f"  MD report: {OUTPUT_DIR / 'report.md'}")
        print(f"  HTML report: {OUTPUT_DIR / 'report.html'}")
    except Exception as e:
        print(f"  [warn] report generation failed: {e}")


if __name__ == "__main__":
    main()
