"""
General tree with depth-first search (DFS), for the department structure.

How it works:
- A tree is made of nodes. Each node has a label, an optional value and a plain list of children.
  The department tree has four levels: Department -> Batch -> Semester -> Section. Only cohorts
  that really exist appear, because the tree is built from one flat row per cohort.
- build_department_tree(rows): for each row, walk down from the root, reusing the child with the
  right label or creating it, and add the row's counts to the section at the bottom. Then every
  node's children are put in order with merge sort (batch name, semester number, section name).
- dfs_totals(node): depth-first search. A node's total is its own counts plus the totals of its
  children, so each child's subtree is finished before its parent's total is complete. Every
  node is visited exactly once.
- preorder(node) lists each node before its children (the order an outline is read in), and
  dfs_paths(node) gives the path of labels from the root to each node.

Complexity (n = nodes in the tree, r = rows, c = children of one node, d = depth, here 4):
- add_child: O(1). find_child: O(c), a scan of the child list.
- build_department_tree: O(r * d * c) to insert, plus O(n log n) to order all the children.
- dfs_totals and preorder: O(n) time, O(n) space for the result, O(d) for the recursion.
- dfs_paths: O(n * d) time and space, because each path holds up to d labels.
"""

from .sorting import merge_sort


class CohortCounts:
    """The numbers stored on a section node."""

    def __init__(self, students=0, active_students=0, open_complaints=0):
        self.students = students
        self.active_students = active_students
        self.open_complaints = open_complaints


class CohortRow:
    """One flat input row: an exact batch + semester + section cohort and its counts."""

    def __init__(self, batch, semester, section, students=0, active_students=0, open_complaints=0):
        self.batch = batch
        self.semester = semester
        self.section = section
        self.students = students
        self.active_students = active_students
        self.open_complaints = open_complaints


class TreeNode:
    def __init__(self, label, value=None, sort_key=None):
        self.label = label
        self.value = value
        self.sort_key = label if sort_key is None else sort_key
        self.children = []

    def add_child(self, node):
        self.children.append(node)
        return node

    def find_child(self, label):
        for child in self.children:
            if child.label == label:
                return child
        return None


class NodeTotals:
    """One node's subtree totals, with the same shape as the tree (for rendering an outline)."""

    def __init__(self, node, depth):
        self.node = node
        self.label = node.label
        self.depth = depth
        self.students = 0
        self.active_students = 0
        self.open_complaints = 0
        self.children = []

    def add(self, counts):
        self.students += counts.students
        self.active_students += counts.active_students
        self.open_complaints += counts.open_complaints


def _child(parent, label, sort_key):
    node = parent.find_child(label)
    if node is None:
        node = parent.add_child(TreeNode(label, sort_key=sort_key))
    return node


def _node_sort_key(node):
    return node.sort_key


def _order_children(node):
    node.children = merge_sort(node.children, key=_node_sort_key)
    for child in node.children:
        _order_children(child)


def build_department_tree(rows, department="Department"):
    """The Department -> Batch -> Semester -> Section tree of these cohort rows, in order."""
    root = TreeNode(department)
    for row in rows:
        batch = _child(root, row.batch, row.batch)
        semester = _child(batch, f"Semester {row.semester}", row.semester)
        section = _child(semester, f"Section {row.section}", row.section)
        if section.value is None:
            section.value = CohortCounts()
        section.value.students += row.students
        section.value.active_students += row.active_students
        section.value.open_complaints += row.open_complaints
    _order_children(root)
    return root


def _visit_totals(node, depth, result):
    entry = NodeTotals(node, depth)
    result.append(entry)  # placed before its children: the result reads in preorder
    if node.value is not None:
        entry.add(node.value)
    for child in node.children:
        child_entry = _visit_totals(child, depth + 1, result)
        entry.children.append(child_entry)
        entry.add(child_entry)
    return entry


def dfs_totals(node):
    """Every node's subtree totals as a preorder list of NodeTotals; the first is `node` itself.
    An empty tree (None) gives an empty list."""
    result = []
    if node is not None:
        _visit_totals(node, 0, result)
    return result


def preorder(node):
    """Each node before its children, as a list of (node, depth) pairs."""
    result = []
    if node is None:
        return result
    stack = [(node, 0)]
    while stack:
        current, depth = stack.pop()
        result.append((current, depth))
        index = len(current.children) - 1
        while index >= 0:  # pushed last-to-first, so the first child is visited next
            stack.append((current.children[index], depth + 1))
            index -= 1
    return result


def dfs_paths(node):
    """The labels from `node` to each node below it, in preorder."""
    result = []
    if node is None:
        return result
    stack = [(node, [node.label])]
    while stack:
        current, path = stack.pop()
        result.append(path)
        index = len(current.children) - 1
        while index >= 0:
            child = current.children[index]
            stack.append((child, path + [child.label]))
            index -= 1
    return result
