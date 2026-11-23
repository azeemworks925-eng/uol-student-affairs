"""Edit distance: edge cases, and 200 random pairs against a simple full-table reference."""

import random

from django.test import SimpleTestCase

from dsa.edit_distance import find_similar, levenshtein, normalise, similarity


def reference_distance(a, b):
    """The textbook full table. Tests may use built-ins; the implementation may not."""
    table = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        table[i][0] = i
    for j in range(len(b) + 1):
        table[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            table[i][j] = min(table[i - 1][j] + 1, table[i][j - 1] + 1, table[i - 1][j - 1] + cost)
    return table[len(a)][len(b)]


class LevenshteinTests(SimpleTestCase):
    def test_empty_strings(self):
        self.assertEqual(levenshtein("", ""), 0)
        self.assertEqual(levenshtein("abc", ""), 3)
        self.assertEqual(levenshtein("", "abc"), 3)

    def test_identical(self):
        self.assertEqual(levenshtein("section", "section"), 0)

    def test_single_edits(self):
        self.assertEqual(levenshtein("cat", "cart"), 1)  # insert
        self.assertEqual(levenshtein("cart", "cat"), 1)  # delete
        self.assertEqual(levenshtein("cat", "cut"), 1)  # substitute

    def test_classic_examples(self):
        self.assertEqual(levenshtein("kitten", "sitting"), 3)
        self.assertEqual(levenshtein("flaw", "lawn"), 2)
        self.assertEqual(levenshtein("abc", "xyz"), 3)

    def test_is_case_sensitive_and_symmetric(self):
        self.assertEqual(levenshtein("A", "a"), 1)
        self.assertEqual(levenshtein("sunday", "saturday"), levenshtein("saturday", "sunday"))

    def test_200_random_pairs_match_the_reference(self):
        rng = random.Random(324)
        for _ in range(200):
            a = "".join(rng.choice("abcd ") for _ in range(rng.randint(0, 25)))
            b = "".join(rng.choice("abcd ") for _ in range(rng.randint(0, 25)))
            with self.subTest(a=a, b=b):
                self.assertEqual(levenshtein(a, b), reference_distance(a, b))


class SimilarityTests(SimpleTestCase):
    def test_normalise(self):
        self.assertEqual(normalise("  Lab   TIMETABLE \n clash "), "lab timetable clash")
        self.assertEqual(normalise(None), "")

    def test_ignores_case_and_spacing(self):
        self.assertEqual(similarity("Lab  Timetable", " lab timetable "), 1.0)

    def test_bounds(self):
        self.assertEqual(similarity("", ""), 1.0)
        self.assertEqual(similarity("abc", ""), 0.0)
        self.assertEqual(similarity("abc", "xyz"), 0.0)

    def test_value(self):
        self.assertAlmostEqual(similarity("cat", "cut"), 2 / 3)


class FindSimilarTests(SimpleTestCase):
    def test_orders_by_similarity_highest_first(self):
        found = find_similar("projector broken", ["projector is broken", "projector broken!", "water cooler"])
        self.assertEqual(found, ["projector broken!", "projector is broken"])

    def test_threshold_is_inclusive(self):
        self.assertEqual(find_similar("abcde", ["abcxy"], threshold=0.6), ["abcxy"])  # exactly 0.6
        self.assertEqual(find_similar("abcde", ["abcxy"], threshold=0.61), [])

    def test_limit(self):
        self.assertEqual(len(find_similar("same", ["same"] * 5)), 3)
        self.assertEqual(len(find_similar("same", ["same"] * 5, limit=2)), 2)

    def test_ties_keep_their_original_order(self):
        self.assertEqual(find_similar("abcd", ["abcx", "abcy", "abcz"], limit=3), ["abcx", "abcy", "abcz"])

    def test_blank_title_and_no_candidates(self):
        self.assertEqual(find_similar("   ", ["anything", ""]), [])
        self.assertEqual(find_similar("title", []), [])

    def test_key_returns_the_original_records(self):
        records = [{"title": "Water cooler empty"}, {"title": "Projector broken"}]
        self.assertEqual(find_similar("water cooler is empty", records, key=lambda r: r["title"]), [records[0]])
