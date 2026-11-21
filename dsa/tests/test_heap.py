import heapq
import random
from unittest import TestCase

from dsa.heap import MinHeap


class MinHeapTests(TestCase):
    def test_empty(self):
        heap = MinHeap()
        self.assertEqual(len(heap), 0)
        with self.assertRaises(IndexError):
            heap.pop()
        with self.assertRaises(IndexError):
            heap.peek()

    def test_push_pop_peek(self):
        heap = MinHeap()
        for priority, value in ((5, "e"), (1, "a"), (3, "c"), (2, "b"), (4, "d")):
            heap.push(priority, value)
        self.assertEqual(heap.peek(), (1, "a"))
        self.assertEqual(len(heap), 5)
        self.assertEqual([heap.pop()[1] for _ in range(5)], ["a", "b", "c", "d", "e"])
        self.assertEqual(len(heap), 0)

    def test_equal_priorities_come_out_in_push_order(self):
        heap = MinHeap()
        for value in ("first", "second", "third"):
            heap.push(7, value)
        heap.push(1, "urgent")
        self.assertEqual([heap.pop()[1] for _ in range(4)], ["urgent", "first", "second", "third"])

    def test_heap_rule_holds_after_every_operation(self):
        heap, rng = MinHeap(), random.Random(1)

        def check():
            items = heap._items
            for i in range(1, len(items)):
                self.assertFalse(heap._less(i, (i - 1) // 2), "a child is smaller than its parent")

        for _ in range(50):
            heap.push(rng.randint(0, 9), None)
            check()
        while len(heap):
            heap.pop()
            check()

    def test_tuple_priorities(self):
        heap = MinHeap()
        heap.push(("2026-11-02", 9), "later")
        heap.push(("2026-11-01", 12), "earlier")
        self.assertEqual(heap.pop(), (("2026-11-01", 12), "earlier"))

    def test_random_against_heapq(self):
        rng = random.Random(2026)
        for _ in range(200):
            heap, oracle = MinHeap(), []
            for step in range(rng.randint(0, 60)):
                if oracle and rng.random() < 0.4:
                    self.assertEqual(heap.pop()[0], heapq.heappop(oracle)[0])
                else:
                    priority = rng.randint(0, 30)
                    heap.push(priority, step)
                    heapq.heappush(oracle, (priority, step))
                self.assertEqual(len(heap), len(oracle))
                if oracle:
                    self.assertEqual(heap.peek()[0], oracle[0][0])
