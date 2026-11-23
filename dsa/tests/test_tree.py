import random

from django.test import SimpleTestCase

from dsa.tree import CohortRow, TreeNode, build_department_tree, dfs_paths, dfs_totals, preorder


def labels(node):
    return [child.label for child in node.children]


class TreeNodeTests(SimpleTestCase):
    def test_add_and_find_child(self):
        root = TreeNode("root")
        child = root.add_child(TreeNode("a", value=1))
        self.assertIs(root.find_child("a"), child)
        self.assertIsNone(root.find_child("b"))
        self.assertEqual(child.children, [])


class BuildDepartmentTreeTests(SimpleTestCase):
    def test_children_are_ordered_at_every_level(self):
        root = build_department_tree([
            CohortRow("Spring 2025", 10, "B"), CohortRow("Fall 2024", 10, "B"), CohortRow("Fall 2024", 2, "C"),
            CohortRow("Fall 2024", 10, "A"),
        ], "Software Engineering")
        self.assertEqual(root.label, "Software Engineering")
        self.assertEqual(labels(root), ["Fall 2024", "Spring 2025"])
        fall = root.find_child("Fall 2024")
        self.assertEqual(labels(fall), ["Semester 2", "Semester 10"])  # by number, not as text
        self.assertEqual(labels(fall.find_child("Semester 10")), ["Section A", "Section B"])

    def test_only_existing_cohorts_appear(self):
        root = build_department_tree([CohortRow("Fall 2024", 4, "A"), CohortRow("Spring 2025", 5, "B")])
        self.assertIsNone(root.find_child("Fall 2024").find_child("Semester 5"))
        self.assertIsNone(root.find_child("Spring 2025").find_child("Semester 4"))

    def test_repeated_row_adds_to_the_same_section(self):
        root = build_department_tree([CohortRow("F", 1, "A", 2, 1, 1), CohortRow("F", 1, "A", 3, 3, 0)])
        section = root.find_child("F").find_child("Semester 1").find_child("Section A")
        self.assertEqual((section.value.students, section.value.active_students, section.value.open_complaints), (5, 4, 1))


class DfsTotalsTests(SimpleTestCase):
    def test_none_is_empty(self):
        self.assertEqual(dfs_totals(None), [])
        self.assertEqual(preorder(None), [])
        self.assertEqual(dfs_paths(None), [])

    def test_empty_tree_totals_zero(self):
        entries = dfs_totals(build_department_tree([]))
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0].students, entries[0].active_students, entries[0].open_complaints), (0, 0, 0))

    def test_one_branch(self):
        entries = dfs_totals(build_department_tree([CohortRow("F", 4, "A", 3, 2, 1)]))
        self.assertEqual([e.depth for e in entries], [0, 1, 2, 3])
        for entry in entries:
            self.assertEqual((entry.students, entry.active_students, entry.open_complaints), (3, 2, 1))

    def test_several_batches_and_inactive_students(self):
        entries = dfs_totals(build_department_tree([
            CohortRow("F", 4, "A", 5, 3, 2), CohortRow("F", 4, "B", 2, 2, 0), CohortRow("S", 1, "A", 4, 0, 1),
        ]))
        by_label = [(e.label, e.students, e.active_students, e.open_complaints) for e in entries]
        self.assertEqual(by_label, [
            ("Department", 11, 5, 3), ("F", 7, 5, 2), ("Semester 4", 7, 5, 2), ("Section A", 5, 3, 2),
            ("Section B", 2, 2, 0), ("S", 4, 0, 1), ("Semester 1", 4, 0, 1), ("Section A", 4, 0, 1),
        ])

    def test_entries_mirror_the_tree(self):
        root_entry = dfs_totals(build_department_tree([CohortRow("F", 4, "A"), CohortRow("F", 5, "A")]))[0]
        self.assertEqual([c.label for c in root_entry.children[0].children], ["Semester 4", "Semester 5"])

    def test_random_trees_match_a_plain_sum(self):
        rng = random.Random(20261124)
        for _ in range(200):
            rows = [CohortRow(f"B{rng.randint(1, 4)}", rng.randint(1, 8), rng.choice("ABC"),
                              rng.randint(0, 9), rng.randint(0, 9), rng.randint(0, 9))
                    for _ in range(rng.randint(0, 25))]
            root = build_department_tree(rows)
            top = dfs_totals(root)[0]
            self.assertEqual(top.students, sum(r.students for r in rows))
            self.assertEqual(top.active_students, sum(r.active_students for r in rows))
            self.assertEqual(top.open_complaints, sum(r.open_complaints for r in rows))
            self.assertEqual(labels(root), sorted({r.batch for r in rows}))
            self.assertEqual(len(preorder(root)), len(dfs_totals(root)))


class TraversalTests(SimpleTestCase):
    def test_preorder_and_paths(self):
        root = build_department_tree([CohortRow("F", 4, "B"), CohortRow("F", 4, "A")], "D")
        self.assertEqual([(n.label, d) for n, d in preorder(root)],
                         [("D", 0), ("F", 1), ("Semester 4", 2), ("Section A", 3), ("Section B", 3)])
        self.assertEqual(dfs_paths(root)[-1], ["D", "F", "Semester 4", "Section B"])
