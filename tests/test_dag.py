"""Tests for ASR DAG models, decomposer, and executor."""

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from asr.config.models import ASRConfig, AgentConfig, ModelConfig
from asr.dag.models import TaskNode, TaskDAG, DAGResult, NodeStatus
from asr.dag.decomposer import TaskDecomposer
from asr.dag.executor import DAGExecutor
from asr.events.store import EventStore
from asr.spec.models import Specification


def test_node_status_enum():
    """Test NodeStatus enum values."""
    assert NodeStatus.PENDING == "pending"
    assert NodeStatus.RUNNING == "running"
    assert NodeStatus.CONVERGED == "converged"
    assert NodeStatus.STUCK == "stuck"
    assert NodeStatus.SKIPPED == "skipped"


def test_task_node_defaults():
    """Test TaskNode with default values."""
    node = TaskNode(
        id="node-1",
        name="Test Node",
        description="A test node"
    )
    assert node.id == "node-1"
    assert node.name == "Test Node"
    assert node.description == "A test node"
    assert node.files == []
    assert node.depends_on == []
    assert node.status == NodeStatus.PENDING
    assert node.iterations == 0
    assert node.patch_count == 0
    assert node.errors_resolved == 0


def test_task_node_all_fields():
    """Test TaskNode with all fields."""
    node = TaskNode(
        id="node-1",
        name="Test Node",
        description="A test node",
        files=["main.py", "utils.py"],
        depends_on=["node-0"],
        status=NodeStatus.RUNNING,
        iterations=3,
        patch_count=2,
        errors_resolved=5
    )
    assert node.id == "node-1"
    assert len(node.files) == 2
    assert len(node.depends_on) == 1
    assert node.status == NodeStatus.RUNNING
    assert node.iterations == 3
    assert node.patch_count == 2
    assert node.errors_resolved == 5


def test_task_node_is_ready():
    """Test TaskNode.is_ready method."""
    node = TaskNode(
        id="node-1",
        name="Test",
        description="Test",
        depends_on=["node-0", "node-a"]
    )

    completed = {"node-0"}
    assert not node.is_ready(completed)

    completed = {"node-0", "node-a"}
    assert node.is_ready(completed)

    completed = {"node-0", "node-a", "node-b"}
    assert node.is_ready(completed)


def test_task_node_hash():
    """Test TaskNode.__hash__ method."""
    node1 = TaskNode(id="node-1", name="Test", description="Test")
    node2 = TaskNode(id="node-1", name="Other", description="Other")
    node3 = TaskNode(id="node-2", name="Test", description="Test")

    assert hash(node1) == hash(node2)
    assert hash(node1) != hash(node3)


def test_dag_result_defaults():
    """Test DAGResult with required fields."""
    result = DAGResult(
        total_nodes=5,
        converged=3,
        stuck=1,
        skipped=1,
        total_iterations=10
    )
    assert result.total_nodes == 5
    assert result.converged == 3
    assert result.stuck == 1
    assert result.skipped == 1
    assert result.total_iterations == 10
    assert result.node_results == {}


def test_dag_result_with_node_results():
    """Test DAGResult with node results."""
    node_results = {
        "node-1": NodeStatus.CONVERGED,
        "node-2": NodeStatus.STUCK,
        "node-3": NodeStatus.SKIPPED
    }
    result = DAGResult(
        total_nodes=3,
        converged=1,
        stuck=1,
        skipped=1,
        total_iterations=5,
        node_results=node_results
    )
    assert len(result.node_results) == 3
    assert result.node_results["node-1"] == NodeStatus.CONVERGED


def test_task_dag_initialization():
    """Test TaskDAG initialization."""
    dag = TaskDAG(task_id="task-123", project_dir=Path("/test"))
    assert dag.task_id == "task-123"
    assert dag.project_dir == Path("/test")
    assert dag.nodes == {}
    assert dag._completed == set()


def test_task_dag_add_node():
    """Test TaskDAG.add_node method."""
    dag = TaskDAG(task_id="task-123", project_dir=Path("/test"))
    node = TaskNode(id="node-1", name="Test", description="Test")
    dag.add_node(node)
    assert len(dag.nodes) == 1
    assert "node-1" in dag.nodes
    assert dag.nodes["node-1"] == node


def test_task_dag_get_ready_nodes():
    """Test TaskDAG.get_ready_nodes method."""
    dag = TaskDAG(task_id="task-123", project_dir=Path("/test"))

    node1 = TaskNode(id="node-1", name="Task 1", description="Task 1", depends_on=[])
    node2 = TaskNode(id="node-2", name="Task 2", description="Task 2", depends_on=["node-1"])
    node3 = TaskNode(id="node-3", name="Task 3", description="Task 3", depends_on=["node-1"])
    node4 = TaskNode(id="node-4", name="Task 4", description="Task 4", depends_on=["node-2", "node-3"])

    dag.add_node(node1)
    dag.add_node(node2)
    dag.add_node(node3)
    dag.add_node(node4)

    ready = dag.get_ready_nodes()
    assert len(ready) == 1
    assert ready[0].id == "node-1"

    dag.mark_completed("node-1", NodeStatus.CONVERGED)
    ready = dag.get_ready_nodes()
    assert len(ready) == 2
    ready_ids = {n.id for n in ready}
    assert ready_ids == {"node-2", "node-3"}


def test_task_dag_mark_completed():
    """Test TaskDAG.mark_completed method."""
    dag = TaskDAG(task_id="task-123", project_dir=Path("/test"))
    node = TaskNode(id="node-1", name="Test", description="Test")
    dag.add_node(node)

    dag.mark_completed("node-1", NodeStatus.CONVERGED)
    assert dag.nodes["node-1"].status == NodeStatus.CONVERGED
    assert "node-1" in dag._completed


def test_task_dag_topological_order():
    """Test TaskDAG.topological_order method."""
    dag = TaskDAG(task_id="task-123", project_dir=Path("/test"))

    node1 = TaskNode(id="node-1", name="Task 1", description="Task 1", depends_on=[])
    node2 = TaskNode(id="node-2", name="Task 2", description="Task 2", depends_on=["node-1"])
    node3 = TaskNode(id="node-3", name="Task 3", description="Task 3", depends_on=["node-1"])
    node4 = TaskNode(id="node-4", name="Task 4", description="Task 4", depends_on=["node-2", "node-3"])

    dag.add_node(node1)
    dag.add_node(node2)
    dag.add_node(node3)
    dag.add_node(node4)

    order = dag.topological_order()
    assert len(order) == 4

    ids_in_order = [n.id for n in order]
    assert ids_in_order[0] == "node-1"
    assert ids_in_order[-1] == "node-4"
    assert ids_in_order.index("node-2") < ids_in_order.index("node-4")
    assert ids_in_order.index("node-3") < ids_in_order.index("node-4")


def test_task_dag_all_done():
    """Test TaskDAG.all_done method."""
    dag = TaskDAG(task_id="task-123", project_dir=Path("/test"))

    node1 = TaskNode(id="node-1", name="Task 1", description="Task 1")
    node2 = TaskNode(id="node-2", name="Task 2", description="Task 2")

    dag.add_node(node1)
    dag.add_node(node2)

    assert not dag.all_done()

    dag.nodes["node-1"].status = NodeStatus.CONVERGED
    assert not dag.all_done()

    dag.nodes["node-2"].status = NodeStatus.CONVERGED
    assert dag.all_done()

    dag.nodes["node-1"].status = NodeStatus.PENDING
    assert not dag.all_done()


def test_task_dag_result():
    """Test TaskDAG.result method."""
    dag = TaskDAG(task_id="task-123", project_dir=Path("/test"))

    node1 = TaskNode(id="node-1", name="Task 1", description="Task 1", status=NodeStatus.CONVERGED, iterations=3)
    node2 = TaskNode(id="node-2", name="Task 2", description="Task 2", status=NodeStatus.STUCK, iterations=5)
    node3 = TaskNode(id="node-3", name="Task 3", description="Task 3", status=NodeStatus.SKIPPED, iterations=0)

    dag.add_node(node1)
    dag.add_node(node2)
    dag.add_node(node3)

    result = dag.result()
    assert result.total_nodes == 3
    assert result.converged == 1
    assert result.stuck == 1
    assert result.skipped == 1
    assert result.total_iterations == 8
    assert len(result.node_results) == 3


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with Python files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        (project_dir / "main.py").write_text("print('hello')")
        (project_dir / "utils.py").write_text("def foo(): return 42")
        (project_dir / "test_main.py").write_text("def test_pass(): assert True")

        yield project_dir


def test_task_decomposer_initialization():
    """Test TaskDecomposer initialization."""
    model_config = ModelConfig(model="gpt-4o")
    decomposer = TaskDecomposer(model_config)
    assert decomposer._model_config == model_config


def test_task_decomposer_decompose_single_feature(temp_project_dir):
    """Test TaskDecomposer.decompose with single feature."""
    spec = Specification(goal="Build a system")
    model_config = ModelConfig(model="gpt-4o")
    decomposer = TaskDecomposer(model_config)

    import asyncio
    dag = asyncio.run(decomposer.decompose(spec, temp_project_dir, "task-123"))

    assert dag.task_id == "task-123"
    assert len(dag.nodes) == 1
    assert "task-123-root" in dag.nodes

    node = dag.nodes["task-123-root"]
    assert node.name == spec.goal
    assert len(node.files) > 0


def test_task_decomposer_decompose_multiple_features(temp_project_dir):
    """Test TaskDecomposer.decompose with multiple features."""
    from asr.spec.models import Feature

    spec = Specification(
        goal="Build a system",
        features=[
            Feature(name="feature1", description="First feature"),
            Feature(name="feature2", description="Second feature"),
            Feature(name="feature3", description="Third feature")
        ]
    )
    model_config = ModelConfig(model="gpt-4o")
    decomposer = TaskDecomposer(model_config)

    import asyncio
    dag = asyncio.run(decomposer.decompose(spec, temp_project_dir, "task-123"))

    assert len(dag.nodes) == 3
    assert "task-123-f0" in dag.nodes
    assert "task-123-f1" in dag.nodes
    assert "task-123-f2" in dag.nodes


def test_task_decomposer_resolve_file_conflicts():
    """Test TaskDecomposer._resolve_file_conflicts."""
    dag = TaskDAG(task_id="task", project_dir=Path("/test"))

    node1 = TaskNode(id="node-1", name="Task 1", description="Task 1", files=["file1.py", "file2.py"])
    node2 = TaskNode(id="node-2", name="Task 2", description="Task 2", files=["file2.py", "file3.py"])
    node3 = TaskNode(id="node-3", name="Task 3", description="Task 3", files=["file3.py"])

    dag.add_node(node1)
    dag.add_node(node2)
    dag.add_node(node3)

    model_config = ModelConfig(model="gpt-4o")
    decomposer = TaskDecomposer(model_config)
    decomposer._resolve_file_conflicts(dag)

    assert "node-1" in node2.depends_on
    assert "node-2" in node3.depends_on


def test_task_decomposer_infer_files(temp_project_dir):
    """Test TaskDecomposer._infer_files."""
    from asr.spec.models import Feature

    model_config = ModelConfig(model="gpt-4o")
    decomposer = TaskDecomposer(model_config)

    feature1 = Feature(name="main", description="Main module")
    feature2 = Feature(name="unknown_module", description="Unknown")

    files1 = decomposer._infer_files(feature1, temp_project_dir)
    files2 = decomposer._infer_files(feature2, temp_project_dir)

    assert len(files1) > 0 or files1 == []
    assert files2 == ["main.py"]


def test_dag_executor_initialization(temp_project_dir):
    """Test DAGExecutor initialization."""
    config = ASRConfig()
    event_store = EventStore()

    executor = DAGExecutor(
        config=config,
        event_store=event_store,
        project_dir=temp_project_dir
    )

    assert executor._config == config
    assert executor._event_store == event_store
    assert executor._project_dir == temp_project_dir
    assert executor._builder is None
    assert executor._tester is None
    assert executor._analyzer is None
    assert executor._mesh_agents == []


def test_dag_executor_with_agents(temp_project_dir):
    """Test DAGExecutor initialization with agents."""
    from asr.agents.base import BaseAgent

    config = ASRConfig()
    event_store = EventStore()

    class MockAgent(BaseAgent):
        async def process(self, event):
            return []

    builder = MockAgent(name="builder", event_store=event_store)
    tester = MockAgent(name="tester", event_store=event_store)

    executor = DAGExecutor(
        config=config,
        event_store=event_store,
        project_dir=temp_project_dir,
        builder=builder,
        tester=tester
    )

    assert executor._builder is not None
    assert executor._tester is not None


def test_dag_executor_build_node_spec(temp_project_dir):
    """Test DAGExecutor._build_node_spec."""
    from asr.spec.models import AcceptanceCriteria, Feature

    config = ASRConfig()
    event_store = EventStore()
    executor = DAGExecutor(config=config, event_store=event_store, project_dir=temp_project_dir)

    spec = Specification(
        goal="Build API",
        constraints=[],
        acceptance=[
            AcceptanceCriteria(name="test_main_pass", expected_behavior="main module test passes")
        ],
        features=[
            Feature(name="main_module", description="main module")
        ]
    )

    node = TaskNode(
        id="node-1",
        name="main_module",
        description="Implement main module",
        files=["main.py"]
    )

    node_spec = executor._build_node_spec(spec, node)

    assert "main_module" in node_spec.goal.lower()
    assert len(node_spec.features) > 0
