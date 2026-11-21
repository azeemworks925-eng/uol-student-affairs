import random
from unittest import TestCase

from dsa.trie import Trie


class TrieTests(TestCase):
    def test_empty(self):
        trie = Trie()
        self.assertEqual(trie.starts_with("a"), [])
        self.assertEqual(trie.starts_with(""), [])
        self.assertEqual(len(trie), 0)

    def test_prefixes_and_case(self):
        trie = Trie()
        trie.insert("Ali Khan", 1)
        trie.insert("Alina", 2)
        trie.insert("Bilal", 3)
        trie.insert("12345678", 1)
        self.assertEqual(sorted(trie.starts_with("ali")), [1, 2])
        self.assertEqual(trie.starts_with("ALI K"), [1])
        self.assertEqual(trie.starts_with("ali khan"), [1])
        self.assertEqual(trie.starts_with("ali khan!"), [])
        self.assertEqual(trie.starts_with("1234"), [1])
        self.assertEqual(trie.starts_with("x"), [])
        self.assertEqual(sorted(trie.starts_with("")), [1, 1, 2, 3])
        self.assertEqual(len(trie), 4)

    def test_word_that_is_a_prefix_of_another(self):
        trie = Trie()
        trie.insert("ali", "a")
        trie.insert("alia", "b")
        self.assertEqual(sorted(trie.starts_with("ali")), ["a", "b"])
        self.assertEqual(trie.starts_with("alia"), ["b"])

    def test_shared_prefixes_share_nodes(self):
        trie = Trie()
        trie.insert("abc", 1)
        trie.insert("abd", 2)
        self.assertEqual(len(trie.root.children), 1)
        self.assertEqual(len(trie.root.child("a").child("b").children), 2)

    def test_random_against_python(self):
        rng = random.Random(2026)
        for _ in range(200):
            words = ["".join(rng.choice("abcAB1") for _ in range(rng.randint(0, 5))) for _ in range(rng.randint(0, 30))]
            trie = Trie()
            for index, word in enumerate(words):
                trie.insert(word, index)
            prefix = "".join(rng.choice("abc1") for _ in range(rng.randint(0, 3)))
            expected = [i for i, w in enumerate(words) if w.lower().startswith(prefix)]
            self.assertEqual(sorted(trie.starts_with(prefix)), expected, (words, prefix))
