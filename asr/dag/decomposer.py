from __future__ import annotations

import json
from pathlib import Path
from asr.dag.models import TaskNode, TaskDAG
from asr.config.models import ModelConfig
from asr.spec.models import Specification


class TaskDecomposer:
    def __init__(self, model_config: ModelConfig):
        self._model_config = model_config

    async def decompose(
        self, spec: Specification, project_dir: Path, task_id: str
    ) -> TaskDAG:
        dag = TaskDAG(task_id=task_id, project_dir=project_dir)

        if len(spec.features) <= 1:
            root = TaskNode(
                id=f"{task_id}-root",
                name=spec.goal,
                description=spec.goal,
                files=[str(p.relative_to(project_dir)) for p in project_dir.rglob("*.py")
                       if "test_" not in p.name and "__pycache__" not in str(p)],
            )
            dag.add_node(root)
            return dag

        for i, feature in enumerate(spec.features):
            node = TaskNode(
                id=f"{task_id}-f{i}",
                name=feature.name,
                description=feature.description,
                files=self._infer_files(feature, project_dir),
                depends_on=[],
            )
            dag.add_node(node)

        self._resolve_file_conflicts(dag)
        return dag

    async def decompose_from_failures(
        self, failures: list[dict], project_dir: Path, task_id: str
    ) -> TaskDAG:
        dag = TaskDAG(task_id=task_id, project_dir=project_dir)

        failure_groups: dict[str, list[dict]] = {}
        for f in failures:
            nodeid = f.get("nodeid", "unknown")
            key = nodeid.split("::")[0] if "::" in nodeid else "general"
            failure_groups.setdefault(key, []).append(f)

        for i, (key, group) in enumerate(failure_groups.items()):
            node = TaskNode(
                id=f"{task_id}-b{i}",
                name=f"Fix {key}",
                description=f"Fix {len(group)} test failures in {key}",
                files=[key] if key != "general" else [],
                depends_on=[],
            )
            dag.add_node(node)

        self._resolve_file_conflicts(dag)
        return dag

    def _resolve_file_conflicts(self, dag: TaskDAG) -> None:
        file_owners: dict[str, str] = {}
        for node_id, node in dag.nodes.items():
            for f in node.files:
                if f in file_owners and file_owners[f] != node_id:
                    if file_owners[f] not in node.depends_on:
                        node.depends_on.append(file_owners[f])
                else:
                    file_owners[f] = node_id

    def _infer_files(self, feature, project_dir: Path) -> list[str]:
        name_lower = feature.name.lower()
        candidates = []
        for py_file in project_dir.rglob("*.py"):
            if "test_" not in py_file.name and "__pycache__" not in str(py_file):
                rel = str(py_file.relative_to(project_dir))
                if name_lower.replace("_", "") in rel.lower().replace("_", ""):
                    candidates.append(rel)
        return candidates if candidates else ["main.py"]
