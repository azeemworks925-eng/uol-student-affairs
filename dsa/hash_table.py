"""
Hash table with separate chaining, for string keys.

How it works:
- The table is an array of "buckets". Each bucket is a small list (the chain) of [key, value]
  pairs.
- A hash function turns the key into a number; `number % capacity` picks the bucket.
- put: look through that bucket's chain; replace the value if the key is there, otherwise
  append a new pair. get / contains: look through that one chain only.
- Two keys landing in the same bucket (a collision) simply share the chain.
- Load factor = items / buckets. When it goes above 0.75 the array doubles and every pair is
  re-inserted (rehashed), so chains stay short.

Hash function (polynomial rolling hash): start at 0; for each character,
h = (h * 31 + character code) mod 2^32. Different orders of the same letters give different
numbers ("ab" and "ba" differ), and 31 is a small odd prime that spreads keys well.

Complexity (n = items, k = key length):
- put, get, contains: O(k) on average (hash the key, then a chain of about 0.75 items);
  O(k + n) in the worst case, if every key collides into one bucket.
- resize: O(n), but it happens only when the size doubles, so put stays O(k) amortised.
- __len__: O(1).
- space: O(n + capacity).
"""

MAX_LOAD_FACTOR = 0.75
_MOD = 2 ** 32


def string_hash(key):
    """Polynomial rolling hash of a string."""
    h = 0
    for character in key:
        h = (h * 31 + ord(character)) % _MOD
    return h


class HashTable:
    def __init__(self, capacity=8):
        self._capacity = max(1, capacity)
        self._buckets = self._empty_buckets(self._capacity)
        self._size = 0

    @staticmethod
    def _empty_buckets(capacity):
        buckets = []
        for _ in range(capacity):
            buckets.append([])
        return buckets

    def _bucket(self, key):
        return self._buckets[string_hash(key) % self._capacity]

    def put(self, key, value):
        bucket = self._bucket(key)
        for pair in bucket:
            if pair[0] == key:
                pair[1] = value  # existing key: replace its value
                return
        bucket.append([key, value])
        self._size += 1
        if self._size / self._capacity > MAX_LOAD_FACTOR:
            self._resize(self._capacity * 2)

    def get(self, key, default=None):
        for pair in self._bucket(key):
            if pair[0] == key:
                return pair[1]
        return default

    def contains(self, key):
        for pair in self._bucket(key):
            if pair[0] == key:
                return True
        return False

    def __contains__(self, key):
        return self.contains(key)

    def __len__(self):
        return self._size

    @property
    def capacity(self):
        return self._capacity

    @property
    def load_factor(self):
        return self._size / self._capacity

    def _resize(self, new_capacity):
        old_buckets = self._buckets
        self._capacity = new_capacity
        self._buckets = self._empty_buckets(new_capacity)
        for bucket in old_buckets:
            for key, value in bucket:
                self._bucket(key).append([key, value])  # keys are unique: no search needed
