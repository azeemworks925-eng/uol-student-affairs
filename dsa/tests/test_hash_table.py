import random
import string
from unittest import TestCase

from dsa.hash_table import HashTable, string_hash


class HashTableTests(TestCase):
    def test_empty(self):
        table = HashTable()
        self.assertEqual(len(table), 0)
        self.assertIsNone(table.get("missing"))
        self.assertEqual(table.get("missing", "default"), "default")
        self.assertFalse(table.contains("missing"))

    def test_put_get_replace(self):
        table = HashTable()
        table.put("CMP-2026-00001", 1)
        table.put("CMP-2026-00002", 2)
        table.put("CMP-2026-00001", 10)  # replace, not a second entry
        self.assertEqual(len(table), 2)
        self.assertEqual(table.get("CMP-2026-00001"), 10)
        self.assertTrue("CMP-2026-00002" in table)
        self.assertFalse(table.contains("cmp-2026-00002"))  # keys are case-sensitive

    def test_collisions_share_a_bucket(self):
        table = HashTable(capacity=1)
        table._resize = lambda capacity: None  # keep one bucket: every key collides
        for word in ("a", "b", "c"):
            table.put(word, word.upper())
        self.assertEqual([table.get(w) for w in ("a", "b", "c")], ["A", "B", "C"])
        self.assertEqual(len(table._buckets[0]), 3)

    def test_resizes_above_load_factor(self):
        table = HashTable(capacity=4)
        for i in range(3):
            table.put(str(i), i)  # 3 / 4 = 0.75: not above
        self.assertEqual(table.capacity, 4)
        table.put("3", 3)  # 4 / 4 > 0.75: doubles
        self.assertEqual(table.capacity, 8)
        self.assertLessEqual(table.load_factor, 0.75)
        self.assertEqual([table.get(str(i)) for i in range(4)], [0, 1, 2, 3])

    def test_hash_function(self):
        self.assertEqual(string_hash(""), 0)
        self.assertEqual(string_hash("ab"), 97 * 31 + 98)
        self.assertNotEqual(string_hash("ab"), string_hash("ba"))
        self.assertLess(string_hash("x" * 1000), 2 ** 32)

    def test_random_against_python_dict(self):
        rng = random.Random(2026)
        for _ in range(200):
            table, oracle = HashTable(capacity=rng.randint(1, 8)), {}
            for _ in range(rng.randint(0, 80)):
                key = "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(rng.randint(0, 4)))
                value = rng.randint(0, 999)
                table.put(key, value)
                oracle[key] = value
            self.assertEqual(len(table), len(oracle))
            for key, value in oracle.items():
                self.assertEqual(table.get(key), value)
            self.assertLessEqual(table.load_factor, 0.75)
            self.assertFalse(table.contains("not-a-key-!"))
