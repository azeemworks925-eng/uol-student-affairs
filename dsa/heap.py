"""
Binary min-heap, stored in a plain list.

How it works:
- A complete binary tree kept in an array: the node at index i has its children at 2i + 1 and
  2i + 2, and its parent at (i - 1) // 2. No pointers are needed.
- Heap rule: every parent's priority is <= its children's, so the smallest is always at
  index 0.
- push: append at the end (the next free leaf), then "sift up": swap with the parent while
  the new item is smaller.
- pop: take the root, move the last item to the root, then "sift down": swap with the smaller
  child while a child is smaller.
- Items with equal priority come out in the order they were pushed: each entry also records a
  push counter, used as the tie-breaker.

Complexity (n = items in the heap; the tree has about log2 n levels):
- push: O(log n), at most one swap per level going up.
- pop: O(log n), at most one swap per level going down.
- peek, __len__: O(1).
- space: O(n).
"""


class MinHeap:
    def __init__(self):
        self._items = []  # entries: [priority, push_order, value]
        self._pushes = 0

    def push(self, priority, value):
        self._items.append([priority, self._pushes, value])
        self._pushes += 1
        self._sift_up(len(self._items) - 1)

    def peek(self):
        """(priority, value) of the smallest item, without removing it."""
        if not self._items:
            raise IndexError("peek from an empty heap")
        entry = self._items[0]
        return entry[0], entry[2]

    def pop(self):
        """Remove and return (priority, value) of the smallest item."""
        if not self._items:
            raise IndexError("pop from an empty heap")
        top = self._items[0]
        last = self._items.pop()  # removes the last array slot
        if self._items:
            self._items[0] = last
            self._sift_down(0)
        return top[0], top[2]

    def __len__(self):
        return len(self._items)

    def _less(self, i, j):
        """Whether the entry at i comes before the entry at j (priority, then push order)."""
        a, b = self._items[i], self._items[j]
        if a[0] != b[0]:
            return a[0] < b[0]
        return a[1] < b[1]

    def _swap(self, i, j):
        self._items[i], self._items[j] = self._items[j], self._items[i]

    def _sift_up(self, index):
        while index > 0:
            parent = (index - 1) // 2
            if not self._less(index, parent):
                break
            self._swap(index, parent)
            index = parent

    def _sift_down(self, index):
        size = len(self._items)
        while True:
            left, right = 2 * index + 1, 2 * index + 2
            smallest = index
            if left < size and self._less(left, smallest):
                smallest = left
            if right < size and self._less(right, smallest):
                smallest = right
            if smallest == index:
                break
            self._swap(index, smallest)
            index = smallest
