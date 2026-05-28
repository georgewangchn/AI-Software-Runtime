from __future__ import annotations

import asyncio
from pathlib import Path

import click

from asr.config.loader import load_config, create_default_config
from asr.runtime import ASRRuntime
from asr.agents.llm_tracker import get_agent_tokens


@click.group()
def cli():
    pass


@cli.command()
@click.option("--project", required=True, type=click.Path(exists=True), help="Project directory")
@click.option("--spec", default=None, type=click.Path(exists=True), help="Spec YAML file (optional; reads DESIGN.md if omitted)")
@click.option("--config", "config_path", default=None, type=click.Path(exists=True), help="Config YAML file")
@click.option("--max-iterations", default=None, type=int, help="Override max iterations")
@click.option("--decoupled", is_flag=True, help="Use decoupled A2A mode (AgentRunner)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def run(project, spec, config_path, max_iterations, decoupled, verbose):
    from asr.controller.convergence import ConvergenceState

    config = load_config(config_path) if config_path else create_default_config()
    if max_iterations:
        config.convergence.max_iterations = max_iterations

    project_dir = Path(project).resolve()
    spec_path = Path(spec).resolve() if spec else None
    runtime = ASRRuntime(config)

    mode = "解耦A2A" if decoupled else "直接模式"
    click.echo(f"ASR 收敛运行时 [{mode}]")
    click.echo(f"项目路径: {project_dir}")
    click.echo(f"规格文件: {spec_path or '(来自 DESIGN.md)'}")
    click.echo(f"最大迭代轮次: {config.convergence.max_iterations}")
    click.echo()

    async def _run():
        last = [0, 0, 0]

        def progress(iteration, errors, phase, failed, errored, detail=""):
            if iteration != last[0] or phase != last[2]:
                icon = "❌" if (failed or errored) else "✅" if errors == 0 else "🔧"
                label = {"TESTING": "测试验证", "ANALYZING": "规格分析", "BUILDING": "代码生成", "REPAIRING": "代码修复", "GENERATING": "初始生成"}.get(phase, phase)
                agent_key = {"TESTING": "tester", "ANALYZING": "analyzer", "BUILDING": "builder", "REPAIRING": "builder"}.get(phase, "")
                line = f"  [第{iteration}轮] {label}  错误:{errors}  {icon}"
                if agent_key:
                    t = get_agent_tokens(agent_key)
                    if t.get("calls", 0) > 0:
                        inp = _fmt_tokens(t["prompt_tokens"])
                        out = _fmt_tokens(t["completion_tokens"])
                        line += f"  | Token:{inp}/{out}"
                if detail:
                    line += f"  | {detail}"
                click.echo(line)
                last[0] = iteration
                last[1] = errors
                last[2] = phase

        return await runtime.run(project_dir, spec_path, use_decoupled=decoupled, progress_callback=progress)

    result = asyncio.run(_run())

    click.echo()
    dag_info = result.summary.get("dag", {}) if result.summary else {}
    if dag_info:
        click.echo(f"Mode: DAG | Nodes: {dag_info.get('total_nodes', '?')} | Converged: {dag_info.get('converged', '?')} | Stuck: {dag_info.get('stuck', '?')}")
        if result.state == ConvergenceState.STUCK:
            click.echo(f"❌ STUCK — {dag_info.get('stuck', 0)} of {dag_info.get('total_nodes', '?')} nodes failed")
        else:
            click.echo("✅ CONVERGED — all DAG nodes converged")
        click.echo(f"Iterations: {result.iterations}")
    else:
        _show_progress(result)
        click.echo()
        if result.state == ConvergenceState.CONVERGED:
            click.echo("✅ 已收敛 — 所有测试通过且规格一致")
        else:
            reason = result.events[-1].payload.get("reason", "unknown") if result.events else "unknown"
            click.echo(f"❌ 卡住 — {reason}")
        click.echo(f"迭代轮次: {result.iterations} | 事件数: {len(result.events)}")
        click.echo(f"\n📁 详细日志: .runtime/logs/asr.log")
        click.echo(f"📁 LLM 追踪: .runtime/logs/llm.jsonl")


@cli.command(name="run-dag")
@click.option("--project", required=True, type=click.Path(exists=True), help="Project directory")
@click.option("--spec", required=True, type=click.Path(exists=True), help="Spec YAML file")
@click.option("--config", "config_path", default=None, type=click.Path(exists=True), help="Config YAML file")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def run_dag(project, spec, config_path, verbose):
    config = load_config(config_path) if config_path else create_default_config()
    project_dir = Path(project).resolve()
    runtime = ASRRuntime(config)

    click.echo(f"ASR Runtime [DAG Mode]")
    click.echo(f"Project: {project_dir}")
    click.echo()

    async def _run():
        return await runtime.run_dag(project_dir, Path(spec))

    result = asyncio.run(_run())

    click.echo()
    click.echo(f"Nodes: {result.total_nodes} | Converged: {result.converged} | Stuck: {result.stuck}")
    click.echo(f"Total iterations: {result.total_iterations}")
    for nid, status in result.node_results.items():
        icon = "✅" if status.value == "converged" else "❌"
        click.echo(f"  {icon} {nid}: {status.value}")


@cli.command()
@click.option("--project", required=True, type=click.Path(), help="Project directory to initialize")
def init(project):
    import yaml
    project_dir = Path(project)
    project_dir.mkdir(parents=True, exist_ok=True)

    config_path = project_dir / "asr_config.yaml"
    config = create_default_config()
    config_path.write_text(yaml.dump(config.model_dump(), default_flow_style=False))

    runtime_dir = project_dir / ".runtime"
    for sub in ["events", "inbox/builder", "inbox/tester", "inbox/analyzer",
                "tasks", "patches", "diffs", "state"]:
        (runtime_dir / sub).mkdir(parents=True, exist_ok=True)

    click.echo(f"Initialized ASR project at {project_dir}")
    click.echo(f"Config: {config_path}")
    click.echo(f"Runtime: {runtime_dir}")


@cli.command()
@click.option("--project", required=True, type=click.Path(exists=True), help="Project directory")
@click.option("--spec", required=True, type=click.Path(exists=True), help="Spec YAML file")
@click.option("--baseline", default="single", type=click.Choice(["single", "opencode"]), help="Baseline type")
def compare(project, spec, baseline):
    click.echo("Comparison mode (demo harness)")
    click.echo(f"Project: {project}")
    click.echo(f"Baseline: {baseline}")
    click.echo("Run 'python scripts/run_demo.py' for full demo comparison")


def _fmt_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


def _show_progress(result) -> None:
    from asr.events.models import EventType
    events = result.events

    tests = [e for e in events if e.type in (EventType.TEST_FAILED, EventType.TEST_PASSED, EventType.TEST_ERROR)]
    patches = [e for e in events if e.type == EventType.PATCH_GENERATED]
    applied = [e for e in events if e.type == EventType.PATCH_APPLIED]
    success = [e for e in applied if e.payload.get("success")]

    click.echo(f"Tests: {len(tests)} | Patches: {len(patches)} | Applied: {len(success)}/{len(applied)}")

    test_errors = [e for e in tests if e.type == EventType.TEST_ERROR]
    if test_errors:
        click.echo(f"\n⚠️  编译/Lint 错误 ({len(test_errors)} 次):")
        shown = set()
        for e in test_errors:
            msg = e.payload.get("error_message", "")[:150]
            if msg not in shown:
                shown.add(msg)
                click.echo(f"  {msg}")

    iterations = [e for e in events if e.type == EventType.CONVERGENCE_ITERATION]
    if iterations:
        click.echo(f"\n{'Iter':<6} {'Errors':<8} {'Phase':<12} {'Detail'}")
        click.echo("-" * 65)
        for it in iterations:
            p = it.payload if isinstance(it.payload, dict) else {}
            errs = p.get("errors_remaining", "?")
            phase = p.get("phase", "")
            detail = p.get("detail", "")
            click.echo(f"{p.get('iteration', '?'):<6} {str(errs):<8} {phase:<12} {detail}")

    last_test = tests[-1] if tests else None
    if last_test and last_test.type == EventType.TEST_FAILED:
        failures = last_test.payload.get("failures", [])
        if failures:
            click.echo(f"\n剩余测试失败 ({len(failures)}):")
            for f in failures[:10]:
                click.echo(f"  ❌ {f.get('nodeid', '?'):<40} {f.get('message', '?')[:60]}")

    last_patch = patches[-1] if patches else None
    if last_patch:
        diff = last_patch.payload.get("diff_text", "")
        if diff:
            click.echo(f"\n最后一次补丁 (前 200 字符):")
            for line in diff.split("\n")[:6]:
                click.echo(f"  {line[:100]}")


if __name__ == "__main__":
    cli()
