from __future__ import annotations

from pathlib import Path

from asr.config.models import ASRConfig, ModelConfig
from asr.controller.convergence import ASRController, ConvergenceResult, ConvergenceState
from asr.events.store import EventStore
from asr.agents.builder import BuilderAgent
from asr.agents.tester import TesterAgent
from asr.agents.analyzer import AnalyzerAgent
from asr.agents.runner import AgentRunner, AgentOrchestrator
from asr.agents.llm_tracker import log_token_usage
from asr.agents.opencode_backend import opencode_completion
from asr.spec.compiler import SpecCompiler
from asr.dag.decomposer import TaskDecomposer
from asr.dag.executor import DAGExecutor
from asr.logger import ASRLogger
from asr.spec.models import Specification
import yaml, re


class ASRRuntime:
    def __init__(self, config: ASRConfig):
        self._config = config
        self._event_store = EventStore(config.runtime.event_dir)

    async def run(
        self, project_dir: Path, spec_path: Path, use_decoupled: bool = False,
        progress_callback=None,
    ) -> ConvergenceResult:
        with open(spec_path) as f:
            spec = Specification(**yaml.safe_load(f))
        return await self._execute(project_dir, spec, use_decoupled, progress_callback)

    async def run_dag(
        self, project_dir: Path, spec_path: Path, mode: str = "features"
    ):
        with open(spec_path) as f:
            spec = Specification(**yaml.safe_load(f))
        builder = self._create_builder(project_dir)
        tester = self._create_tester(project_dir)
        analyzer = self._create_analyzer(project_dir)
        dag = await TaskDecomposer(self._agent_model()).decompose(spec, project_dir, "dag-0")
        from asr.dag.models import DAGResult
        return await DAGExecutor(
            config=self._config, event_store=self._event_store,
            project_dir=project_dir, builder=builder, tester=tester,
            analyzer=analyzer, mesh_agents=[],
        ).execute(dag, spec)

    async def run_from_nl(
        self, project_dir: Path, natural_language: str, use_decoupled: bool = False
    ) -> ConvergenceResult:
        mc = self._agent_model()
        compiler = SpecCompiler(mc)
        spec = await compiler.compile(natural_language)
        spec_path = project_dir / "spec.yaml"
        spec_path.write_text(yaml.dump(spec.model_dump(), default_flow_style=False, allow_unicode=True))
        return await self._execute(project_dir, spec, use_decoupled)

    async def build(
        self, project_dir: Path, design_path: Path, max_iterations: int = 10
    ) -> ConvergenceResult:
        design_text = design_path.read_text()
        mc = self._agent_model()
        spec = await SpecCompiler(mc).compile(design_text)

        project_dir.mkdir(parents=True, exist_ok=True)
        spec_path = project_dir / "spec.yaml"
        spec_path.write_text(yaml.dump(spec.model_dump(), default_flow_style=False, allow_unicode=True))

        builder = self._create_builder(project_dir)
        if builder:
            from asr.events.models import TaskCreatedEvent, AgentName, EventType
            evt = TaskCreatedEvent(
                task_id="build-0", from_agent=AgentName.CONTROLLER, to_agent=AgentName.BUILDER,
                payload={"spec": spec.model_dump(), "project_path": str(project_dir), "max_iterations": max_iterations},
            )
            results = await builder.process(evt)
            for evt in results:
                if evt.type == EventType.CODE_GENERATED:
                    code_text = evt.payload.get("diff_text", "")
                    if code_text:
                        target = project_dir / (evt.payload.get("file_path") or "main.py")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if "@@" in code_text:
                            from asr.patch.diff import PatchEngine
                            for pr in PatchEngine().apply(code_text, project_dir):
                                if pr.success and pr.content:
                                    target.write_text(pr.content)
                        else:
                            target.write_text(code_text)

        tests_code = await self._generate_tests(spec, mc)
        (project_dir / "test_main.py").write_text(tests_code)

        return await self._execute(project_dir, spec, False, progress_callback=None)

    async def _generate_tests(self, spec, mc) -> str:
        messages = [
            {"role": "system", "content": "Generate pytest tests with fastapi.testclient.TestClient. Import from main. Output ONLY Python code, no markdown."},
            {"role": "user", "content": f"Spec:\n{yaml.dump(spec.model_dump(), allow_unicode=True)}\n\nGenerate pytest tests verifying all features and acceptance criteria."},
        ]
        for attempt in range(3):
            user = messages[-1]["content"] if messages else ""
            system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
            prompt = f"{system}\n\n{user}" if system else user
            text, pt, ct, tt = await opencode_completion(prompt, Path("/tmp"))
            log_token_usage("runtime_test_gen", "opencode/qwen3-next-80b", {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})
            content = text
            content = re.sub(r"```python\s*", "", content)
            content = re.sub(r"```\s*$", "", content)
            content = content.strip()
            if content and "def test_" in content:
                return content
            if attempt < 2:
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": "Invalid. Generate ONLY pytest test functions. No markdown."})
        return content or "# tests failed to generate"

    async def _execute(
        self, project_dir: Path, spec, use_decoupled: bool, progress_callback=None
    ) -> ConvergenceResult:
        builder = self._create_builder(project_dir)
        tester = self._create_tester(project_dir)
        analyzer = self._create_analyzer(project_dir)

        failures = await self._quick_test(project_dir, tester)
        if len(failures) > 1:
            groups: dict[str, list] = {}
            for f in failures:
                key = f.get("nodeid", "unknown").split("::")[0]
                groups.setdefault(key, []).append(f)
            if len(groups) > 1:
                return await self._run_dag(
                    project_dir, spec, builder, tester, analyzer,
                    lambda m: TaskDecomposer(m).decompose_from_failures(failures, project_dir, "auto-dag"),
                )

        if hasattr(spec, 'features') and len(spec.features) > 1:
            nodes = self._preview_nodes(spec, project_dir)
            all_files = {f for n in nodes for f in n.files}
            if len(all_files) > 1:
                return await self._run_dag(
                    project_dir, spec, builder, tester, analyzer,
                    lambda m: TaskDecomposer(m).decompose(spec, project_dir, "auto-dag"),
                )

        controller = ASRController(
            config=self._config,
            event_store=self._event_store,
            project_dir=project_dir,
            builder=builder,
            tester=tester,
            analyzer=analyzer,
            use_decoupled_a2a=use_decoupled,
            logger=ASRLogger(),
        )

        if use_decoupled and (builder or tester or analyzer):
            orchestrator = AgentOrchestrator(self._event_store)
            if builder:
                orchestrator.register("builder", AgentRunner(builder, self._event_store))
            if tester:
                orchestrator.register("tester", AgentRunner(tester, self._event_store))
            if analyzer:
                orchestrator.register("analyzer", AgentRunner(analyzer, self._event_store))
            return await orchestrator.run_until_converged(controller.run(spec))

        return await controller.run(spec, progress_callback=progress_callback)

    def _create_builder(self, project_dir: Path):
        cfg = self._config.get_agent("builder")
        return BuilderAgent(cfg, self._event_store, project_dir) if cfg else None

    def _create_tester(self, project_dir: Path):
        cfg = self._config.get_agent("tester")
        return TesterAgent(cfg, self._event_store, project_dir) if cfg else None

    def _create_analyzer(self, project_dir: Path):
        cfg = self._config.get_agent("analyzer")
        return AnalyzerAgent(cfg, self._event_store, project_dir) if cfg else None

    async def _run_dag(self, project_dir, spec, builder, tester, analyzer, decomposer):
        dag = await decomposer(self._agent_model())
        from asr.dag.models import DAGResult
        dag_result = await DAGExecutor(
            config=self._config, event_store=self._event_store,
            project_dir=project_dir, builder=builder, tester=tester,
            analyzer=analyzer, mesh_agents=[],
        ).execute(dag, spec)
        return ConvergenceResult(
            state=ConvergenceState.CONVERGED if dag_result.stuck == 0 else ConvergenceState.STUCK,
            iterations=dag_result.total_iterations,
            summary={"dag": dag_result.__dict__},
        )

    async def _quick_test(self, project_dir: Path, tester) -> list[dict]:
        if tester is None:
            return []
        try:
            from asr.events.models import TestStartedEvent, AgentName, EventType
            event = TestStartedEvent(
                task_id="quick-test", from_agent=AgentName.CONTROLLER,
                to_agent=AgentName.TESTER, payload={"test_paths": [str(project_dir)]},
            )
            results = await tester.process(event)
            for evt in results:
                if evt.type == EventType.TEST_FAILED:
                    return evt.payload.get("failures", [])
        except Exception:
            pass
        return []

    def _agent_model(self) -> ModelConfig:
        return self._config.agents[0].model if self._config.agents else ModelConfig(model="none")

    def _preview_nodes(self, spec, project_dir: Path) -> list:
        from asr.dag.models import TaskNode
        nodes = []
        for i, feature in enumerate(spec.features):
            name_lower = feature.name.lower()
            candidates = []
            for py_file in project_dir.rglob("*.py"):
                if "test_" not in py_file.name and "__pycache__" not in str(py_file):
                    rel = str(py_file.relative_to(project_dir))
                    if name_lower.replace("_", "") in rel.lower().replace("_", ""):
                        candidates.append(rel)
            nodes.append(TaskNode(
                id=f"preview-{i}", name=feature.name, description="",
                files=candidates or ["main.py"],
            ))
        return nodes
