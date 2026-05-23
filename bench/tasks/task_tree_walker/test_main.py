from main import TreeNode, count_nodes, find_value

def make_tree():
    return TreeNode(1, [
        TreeNode(2, [TreeNode(4), TreeNode(5)]),
        TreeNode(3, [TreeNode(6)]),
    ])

def test_count_nodes():
    tree = make_tree()
    assert count_nodes(tree) == 6

def test_count_empty():
    assert count_nodes(None) == 0

def test_find_value_exists():
    tree = make_tree()
    node = find_value(tree, 5)
    assert node is not None
    assert node.value == 5

def test_find_value_not_exists():
    tree = make_tree()
    assert find_value(tree, 99) is None

def test_find_value_root():
    tree = make_tree()
    node = find_value(tree, 1)
    assert node is not None
    assert node.value == 1
