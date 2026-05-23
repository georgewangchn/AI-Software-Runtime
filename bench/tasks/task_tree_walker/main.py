class TreeNode:
    def __init__(self, value, children=None):
        self.value = value
        self.children = children or []

def count_nodes(root):
    if root is None:
        return 0
    count = 1
    for child in root.children:
        count += count_nodes(child)
    return count

def find_value(root, target):
    if root is None:
        return None
    if root.value == target:
        return root
    for child in root.children:
        result = find_value(child, target)
        if result:
            return result
    return find_value(root, target)
