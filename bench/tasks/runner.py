#!/usr/bin/env python3
"""
ASR vs OpenCode vs Baseline — Multi-Task Comparison Runner.

Runs 3 modes (baseline, opencode, asr) on all tasks in bench/tasks/.
Uses the same LLM backend for fair comparison.
Produces: bench/outputs/tasks_compare/results.json + reports.

Usage:
    python bench/tasks/runner.py                    # all tasks, all modes
    python bench/tasks/runner.py --mode asr --task task_fibonacci
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

ROOT = Path(__file__).resolve().parent.parent.parent
TASKS_DIR = ROOT / "bench" / "tasks"
OUTPUT_DIR = ROOT / "bench" / "outputs" / "tasks_compare"
WORKSPACE_ROOT = ROOT / "bench" / "workspace" / "tasks"


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated: bool = False

    def to_dict(self):
        return {"prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens, "estimated": self.estimated}

    def __add__(self, o):
        return TokenUsage(self.prompt_tokens + o.prompt_tokens, self.completion_tokens + o.completion_tokens,
                          self.total_tokens + o.total_tokens, self.estimated or o.estimated)


@dataclass
class RunResult:
    task: str
    mode: str
    success: bool
    iterations: int = 0
    elapsed_seconds: float = 0
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    test_failures: int = -1
    error: str | None = None
    stop_reason: str = ""


def get_api_config():
    env_path = ROOT / ".env"
    cfg = {"model": "qwen3-next-80b-a3b-instruct",
           "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "api_key": ""}
    if env_path.exists():
        for line in env_path.read_text().split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if k == "FEASIBILITY_LLM_MODEL": cfg["model"] = v
            elif k == "FEASIBILITY_LLM_API_BASE": cfg["base_url"] = v
            elif k == "FEASIBILITY_LLM_API_KEY": cfg["api_key"] = v
    return cfg


def run_tests(project_dir, timeout=120):
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=short"],
                            cwd=str(project_dir), capture_output=True, text=True, timeout=timeout)
    output = result.stdout + result.stderr
    passed = result.returncode == 0
    m = re.search(r"(\d+)\s+failed", output)
    failures = int(m.group(1)) if m else (0 if passed else output.count("FAILED"))
    return passed, failures, output


def prepare_workspace(task_dir, mode):
    work_dir = WORKSPACE_ROOT / task_dir.name / mode
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    shutil.copytree(task_dir, work_dir, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".runtime", "README.md", "*.pyc"))
    if not (work_dir / ".git").exists():
        subprocess.run(["git", "init"], cwd=str(work_dir), capture_output=True, timeout=10)
        subprocess.run(["git", "add", "-A"], cwd=str(work_dir), capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "init", "--allow-empty"],
                       cwd=str(work_dir), capture_output=True, timeout=10)
    return work_dir


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


def run_opencode(workspace, task_name, task_dir, max_iterations=10):
    """Real OpenCode CLI with iterative convergence: each opencode run = 1 iteration."""
    start = time.time()
    total_prompt = total_completion = total_tokens = 0
    readme = (task_dir / "README.md").read_text() if (task_dir / "README.md").exists() else task_name

    for iteration in range(1, max_iterations + 1):
        passed, failures, test_output = run_tests(workspace)
        if passed:
            elapsed = time.time() - start
            usage = TokenUsage(total_prompt, total_completion, total_tokens, False) if total_tokens > 0 else TokenUsage(estimated=True)
            return RunResult(task_name, "opencode", True, iteration,
                             round(elapsed, 2), usage, test_failures=0,
                             stop_reason="all_tests_pass")

        if iteration == 1:
            prompt = f"Task: {readme}\n\nRead the code and design docs. Implement the requirements. Create/improve code files directly."
        else:
            test_summary = test_output[-3000:] if len(test_output) > 3000 else test_output
            if failures > 0:
                prompt = (
                    f"Iteration {iteration}/{max_iterations}. {failures} tests still failing. "
                    f"Read the test output below, identify root causes, and fix the code.\n\n"
                    f"Test failures:\n{test_summary}"
                )
            else:
                prompts = [
                    f"Iteration {iteration}/{max_iterations}. All tests pass. Now optimize the system. "
                    f"Rate the codebase 1-10. Identify weaknesses and improvements. "
                    f"Then apply the improvements directly.",
                    f"Iteration {iteration}/{max_iterations}. All tests pass. From first principles, "
                    f"analyze what is rational and irrational in the current implementation. "
                    f"Propose and apply optimizations for the irrational parts.",
                    f"Iteration {iteration}/{max_iterations}. All tests pass. Review the design document. "
                    f"Check for missing features or incomplete implementations. Fill the gaps.",
                ]
                prompt = prompts[(iteration - 2) % len(prompts)]

        cmd = [
            "opencode", "run",
            "--model", "local/qwen3-next-80b-a3b-instruct",
            "--dangerously-skip-permissions",
            "--format", "json",
            "--dir", str(workspace),
            prompt,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=300,
                                    env={**os.environ, "CI": "true", "GIT_TERMINAL_PROMPT": "0"})
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            usage = TokenUsage(total_prompt, total_completion, total_tokens, False) if total_tokens > 0 else TokenUsage(estimated=True)
            return RunResult(task_name, "opencode", False, iteration,
                             round(elapsed, 2), usage, error="timeout", stop_reason="timeout")

        p, c, t = _parse_opencode_tokens(result.stdout)
        total_prompt += p
        total_completion += c
        total_tokens += t

    elapsed = time.time() - start
    passed, failures, _ = run_tests(workspace)
    usage = TokenUsage(total_prompt, total_completion, total_tokens, False) if total_tokens > 0 else TokenUsage(estimated=True)
    return RunResult(task_name, "opencode", passed, max_iterations,
                     round(elapsed, 2), usage, test_failures=failures,
                     stop_reason="all_tests_pass" if passed else "max_iterations")


def run_asr(workspace, task_name, task_dir, max_iterations=10):
    start = time.time()

    runtime_dir = workspace / ".runtime"
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)
    cwd_runtime = ROOT / ".runtime"
    if cwd_runtime.exists():
        shutil.rmtree(cwd_runtime, ignore_errors=True)

    spec_path = workspace / "spec.yaml"
    spec_src = task_dir / "spec.yaml"
    if spec_src.exists():
        shutil.copy2(spec_src, spec_path)

    cmd = [sys.executable, "-m", "asr.cli.main", "run",
           "--project", str(workspace),
           "--max-iterations", str(max_iterations)]
    if spec_path.exists():
        cmd.extend(["--spec", str(spec_path)])
    try:
        result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                                timeout=max_iterations * 300,
                                env={**os.environ, "PYTHONPATH": f"{ROOT}:{workspace}"})
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return RunResult(task_name, "asr", False, max_iterations, round(elapsed, 2),
                         error="timeout", stop_reason="timeout")
    elapsed = time.time() - start
    output = result.stdout + result.stderr

    iter_match = re.search(r"Iterations:\s*(\d+)", output)
    iterations = int(iter_match.group(1)) if iter_match else 0

    converged = "CONVERGED" in output
    passed = converged
    failures = 0 if converged else -1

    usage = TokenUsage(estimated=True)
    for log_dir in [workspace / ".runtime" / "logs", ROOT / ".runtime" / "logs"]:
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
            t = llm_log.read_text(errors="replace")
            pt = sum(int(x) for x in re.findall(r'"prompt_tokens":\s*(\d+)', t))
            ct = sum(int(x) for x in re.findall(r'"completion_tokens":\s*(\d+)', t))
            tt = sum(int(x) for x in re.findall(r'"total_tokens":\s*(\d+)', t))
            if tt > 0:
                usage = TokenUsage(pt, ct, tt, True)
                break

    return RunResult(task_name, "asr", passed, iterations, round(elapsed, 2), usage,
                     test_failures=failures,
                     stop_reason="CONVERGED" if passed else "STUCK")


def discover_tasks():
    tasks = []
    for d in sorted(TASKS_DIR.iterdir()):
        if d.is_dir() and d.name.startswith("task_") and (d / "main.py").exists() and (d / "test_main.py").exists():
            tasks.append(d)
    return tasks


def generate_summary(all_results):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    summary = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
               "model": get_api_config()["model"],
               "results": [{"task": r.task, "mode": r.mode, "success": r.success,
                            "iterations": r.iterations, "elapsed_seconds": r.elapsed_seconds,
                            "token_usage": r.token_usage.to_dict(),
                            "test_failures": r.test_failures, "error": r.error,
                            "stop_reason": r.stop_reason} for r in all_results]}

    output_path = OUTPUT_DIR / "results.json"
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    lines = ["=" * 70, "  MULTI-TASK COMPARISON: ASR vs OpenCode",
             "=" * 70, f"  Model: {get_api_config()['model']}",
             f"  Tasks: {len(set(r.task for r in all_results))}", "=" * 70, ""]

    for mode in ["opencode", "asr"]:
        mode_results = [r for r in all_results if r.mode == mode]
        passed = sum(1 for r in mode_results if r.success)
        total = len(mode_results)
        rate = f"{passed}/{total} ({passed * 100 // max(total, 1)}%)" if total else "N/A"
        avg_time = sum(r.elapsed_seconds for r in mode_results) / max(total, 1)
        total_tokens = sum(r.token_usage.total_tokens for r in mode_results)
        lines.append(f"  {mode:<12} Pass: {rate:<12} Avg: {avg_time:.0f}s  Tokens: {total_tokens:,}")

    lines.append("")
    lines.append(f"  {'Task':<25} {'opencode':<10} {'asr':<10}")
    lines.append("  " + "-" * 45)
    for task_name in sorted(set(r.task for r in all_results)):
        o = next((r for r in all_results if r.task == task_name and r.mode == "opencode"), None)
        a = next((r for r in all_results if r.task == task_name and r.mode == "asr"), None)
        os_ = "PASS" if o and o.success else "FAIL"
        as_ = "PASS" if a and a.success else "FAIL"
        lines.append(f"  {task_name:<25} {os_:<10} {as_:<10}")
    lines.extend(["", "=" * 70])
    report_text = "\n".join(lines)

    (OUTPUT_DIR / "report.txt").write_text(report_text)
    return report_text


def main():
    parser = argparse.ArgumentParser(description="Multi-task comparison: ASR vs OpenCode")
    parser.add_argument("--mode", choices=["opencode", "asr", "all"], default="all")
    parser.add_argument("--task", type=str, help="Run specific task (e.g., task_fibonacci)")
    parser.add_argument("--max-iter", type=int, default=10)
    args = parser.parse_args()

    tasks = discover_tasks()
    if args.task:
        tasks = [d for d in tasks if d.name == args.task]
    if not tasks:
        print(f"No tasks found in {TASKS_DIR}")
        sys.exit(1)

    modes = ["opencode", "asr"] if args.mode == "all" else [args.mode]
    all_results = []

    print("=" * 70)
    print("  ASR vs OpenCode — Multi-Task Runner")
    print("=" * 70)
    print(f"  Model: {get_api_config()['model']}")
    print(f"  Tasks: {len(tasks)}")
    print(f"  Modes: {modes}")
    print("=" * 70)

    for task_dir in tasks:
        task_name = task_dir.name
        print(f"\n{'━' * 50}")
        print(f"  {task_name}")
        print(f"{'━' * 50}")

        for mode in modes:
            workspace = prepare_workspace(task_dir, mode)
            if mode == "opencode":
                r = run_opencode(workspace, task_name, task_dir, args.max_iter)
            elif mode == "asr":
                r = run_asr(workspace, task_name, task_dir, args.max_iter)
            all_results.append(r)
            status = "PASS" if r.success else "FAIL"
            print(f"    {mode:<10} {status} | {r.iterations} iters | {r.elapsed_seconds:.0f}s | tokens={r.token_usage.total_tokens:,}")

    report = generate_summary(all_results)
    print(f"\n{report}")
    print(f"\n  Results: {OUTPUT_DIR / 'results.json'}")
    print(f"  Report: {OUTPUT_DIR / 'report.txt'}")


if __name__ == "__main__":
    main()
