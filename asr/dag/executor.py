from __future__ import annotations

import asyncio
from pathlib import Path

from asr.config.models import ASRConfig
from asr.controller.convergence import ASRController, ConvergenceState
from asr.events.store import EventStore
from asr.dag.models import TaskNode, TaskDAG, DAGResult, NodeStatus
from asr.spec.models import Specification
from asr.agents.base import BaseAgent


class DAGExecutor:
    def __init__(
        self,
        config: ASRConfig,
        event_store: EventStore,
        project_dir: Path,
        builder: BaseAgent | None = None,
        tester: BaseAgent | None = None,
        analyzer: BaseAgent | None = None,
        mesh_agents: list[BaseAgent] | None = None,
    ):
        self._config = config
        self._event_store = event_store
        self._project_dir = project_dir
        self._builder = builder
        self._tester = tester
        self._analyzer = analyzer
        self._mesh_agents = mesh_agents or []

    async def execute(self, dag: TaskDAG, base_spec: Specification) -> DAGResult:
        while not dag.all_done():
            ready = dag.get_ready_nodes()
            if not ready:
                pending = [n for n in dag.nodes.values() if n.status == NodeStatus.PENDING]
                if pending:
                    break
                continue

            for node in ready:
                dag.nodes[node.id].status = NodeStatus.RUNNING

            tasks = []
            for node in ready:
                tasks.append(self._run_node(dag, node, base_spec))
            await asyncio.gather(*tasks)

        return dag.result()

    async def _run_node(self, dag: TaskDAG, node: TaskNode, base_spec: Specification) -> None:
        node_spec = self._build_node_spec(base_spec, node)
        controller = ASRController(
            config=self._config,
            event_store=self._event_store,
            project_dir=self._project_dir,
            builder=self._builder,
            tester=self._tester,
            analyzer=self._analyzer,
            mesh_agents=self._mesh_agents,
        )
        task_id = f"{dag.task_id}-{node.id}"
        result = await controller.run(node_spec, task_id=task_id)

        node.iterations = result.iterations
        if result.state == ConvergenceState.CONVERGED:
            dag.mark_completed(node.id, NodeStatus.CONVERGED)
        else:
            dag.mark_completed(node.id, NodeStatus.STUCK)

    def _build_node_spec(self, base_spec: Specification, node: TaskNode) -> Specification:
        return Specification(
            goal=f"{base_spec.goal} — {node.name}",
            constraints=base_spec.constraints,
            acceptance=[
                a for a in base_spec.acceptance
                if any(f.replace(".py", "") in a.name.lower() or
                       f.replace("/", ".").replace(".py", "") in a.expected_behavior.lower()
                       for f in node.files)
            ] or base_spec.acceptance,
            features=[
                f for f in base_spec.features
                if f.name.lower().replace("_", "") in node.name.lower().replace("_", "")
            ] or base_spec.features,
        )
