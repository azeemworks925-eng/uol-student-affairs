import random
from unittest import TestCase

from dsa.sorting import merge_sort


class MergeSortTests(TestCase):
    def test_edge_cases(self):
        self.assertEqual(merge_sort([]), [])
        self.assertEqual(merge_sort([7]), [7])
        self.assertEqual(merge_sort([1, 2, 3, 4]), [1, 2, 3, 4])
        self.assertEqual(merge_sort([4, 3, 2, 1]), [1, 2, 3, 4])
        self.assertEqual(merge_sort([3, 1, 3, 1, 2]), [1, 1, 2, 3, 3])
        self.assertEqual(merge_sort([3, 1, 2], reverse=True), [3, 2, 1])
        self.assertEqual(merge_sort(["pear", "Apple", "fig"], key=str.lower), ["Apple", "fig", "pear"])

    def test_returns_a_new_list_and_accepts_any_iterable(self):
        original = [2, 1]
        result = merge_sort(original)
        self.assertEqual(original, [2, 1])
        self.assertIsNot(result, original)
        self.assertEqual(merge_sort(x for x in (3, 2, 1)), [1, 2, 3])

    def test_stable(self):
        items = [("b", 1), ("a", 2), ("b", 3), ("a", 4), ("c", 5), ("a", 6)]
        self.assertEqual(merge_sort(items, key=lambda p: p[0]),
                         [("a", 2), ("a", 4), ("a", 6), ("b", 1), ("b", 3), ("c", 5)])

    def test_stable_with_reverse(self):
        items = [("b", 1), ("a", 2), ("b", 3), ("a", 4), ("c", 5)]
        # Largest key first, but equal keys keep their original order.
        self.assertEqual(merge_sort(items, key=lambda p: p[0], reverse=True),
                         [("c", 5), ("b", 1), ("b", 3), ("a", 2), ("a", 4)])

    def test_two_passes_sort_by_two_keys(self):
        rows = [("x", 2), ("y", 1), ("x", 1), ("y", 2)]
        by_second = merge_sort(rows, key=lambda r: r[1], reverse=True)
        self.assertEqual(merge_sort(by_second, key=lambda r: r[0]), [("x", 2), ("x", 1), ("y", 2), ("y", 1)])

    def test_random_against_python(self):
        rng = random.Random(2026)
        for _ in range(200):
            items = [(rng.randint(0, 20), i) for i in range(rng.randint(0, 60))]
            reverse = rng.random() < 0.5
            with self.subTest(items=items, reverse=reverse):
                expected = sorted(items, key=lambda p: p[0], reverse=reverse)  # Python's sort is stable too
                self.assertEqual(merge_sort(items, key=lambda p: p[0], reverse=reverse), expected)
