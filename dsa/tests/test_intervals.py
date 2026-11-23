"""Interval overlaps: edge cases, plus random cases checked against a brute-force oracle."""

import random
from unittest import TestCase

from dsa.intervals import find_overlaps, overlaps_with


def overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


class FindOverlapsTests(TestCase):
    def test_empty_and_single(self):
        self.assertEqual(find_overlaps([]), [])
        self.assertEqual(find_overlaps([(1, 2, "a")]), [])

    def test_touching_intervals_do_not_overlap(self):
        self.assertEqual(find_overlaps([(10, 20, "a"), (20, 30, "b")]), [])

    def test_finds_a_pair_given_in_any_order(self):
        a, b = (10, 30, "a"), (20, 40, "b")
        self.assertEqual(find_overlaps([b, a]), [(a, b)])

    def test_contained_interval_and_same_start(self):
        outer, inner = (10, 50, "outer"), (20, 30, "inner")
        self.assertEqual(find_overlaps([inner, outer]), [(outer, inner)])
        first, second = (10, 20, "first"), (10, 30, "second")
        self.assertEqual(find_overlaps([first, second]), [(first, second)])

    def test_compares_with_the_latest_end_not_the_previous_interval(self):
        long, short, later = (0, 100, "long"), (10, 20, "short"), (50, 60, "later")
        self.assertEqual(find_overlaps([later, short, long]), [(long, short), (long, later)])

    def test_rejects_an_interval_that_does_not_end_after_it_starts(self):
        for bad in ((5, 5, "empty"), (6, 5, "backwards")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                find_overlaps([bad])

    def test_does_not_change_the_input(self):
        items = [(3, 4, "b"), (1, 2, "a")]
        find_overlaps(items)
        self.assertEqual(items, [(3, 4, "b"), (1, 2, "a")])

    def test_random_every_overlapping_interval_is_reported(self):
        rng = random.Random(7)
        for _ in range(200):
            items = []
            for label in range(rng.randint(0, 25)):
                start = rng.randint(0, 60)
                items.append((start, start + rng.randint(1, 15), label))
            pairs = find_overlaps(items)
            for earlier, later in pairs:
                self.assertTrue(overlap(earlier, later))
            ordered = sorted(items, key=lambda item: item[0])  # stable, as merge sort is
            expected = [b[2] for i, b in enumerate(ordered) if any(overlap(a, b) for a in ordered[:i])]
            self.assertEqual([later[2] for _, later in pairs], expected)


class OverlapsWithTests(TestCase):
    def test_finds_all_even_when_a_long_interval_hides_one(self):
        long, target, hidden = (0, 120, "long"), (10, 20, "target"), (15, 40, "hidden")
        self.assertEqual(overlaps_with(target, [hidden, long]), [long, hidden])

    def test_ignores_overlaps_between_the_other_intervals(self):
        target = (100, 110, "target")
        self.assertEqual(overlaps_with(target, [(0, 30, "a"), (10, 40, "b")]), [])

    def test_target_in_the_list_is_not_its_own_conflict(self):
        target = (10, 20, "target")
        self.assertEqual(overlaps_with(target, [target]), [])

    def test_random_matches_brute_force(self):
        rng = random.Random(11)
        for _ in range(200):
            items = []
            for label in range(rng.randint(0, 20)):
                start = rng.randint(0, 50)
                items.append((start, start + rng.randint(1, 20), label))
            start = rng.randint(0, 50)
            target = (start, start + rng.randint(1, 20), "target")
            found = overlaps_with(target, items)
            self.assertCountEqual([i[2] for i in found], [i[2] for i in items if overlap(target, i)])
            self.assertEqual([i[0] for i in found], sorted(i[0] for i in found))
