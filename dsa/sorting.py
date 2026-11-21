"""
Merge sort.

How it works:
1. Split: a list of 0 or 1 items is already sorted. Otherwise cut it in half and sort each
   half (recursively, with merge sort itself).
2. Merge: walk through the two sorted halves with one finger on each, and repeatedly take the
   item that comes first. When one half runs out, copy the rest of the other.

Stable: when two items have equal keys, the one from the left half is taken first, so equal
items keep their original order. This is also true with reverse=True, because only a strictly
"earlier" key on the right is allowed to jump ahead. Stability lets the portal sort by two
keys: sort by the tie-breaker first, then by the main key.

Complexity (n = number of items):
- time: O(n log n) in every case. Halving gives log n levels; each level merges n items.
- space: O(n) extra, for the merged lists (plus O(log n) for the recursion).
"""


def _identity(item):
    return item


def merge_sort(items, key=None, reverse=False):
    """Return a new sorted list. `key(item)` gives the value to compare (default: the item).
    reverse=True sorts largest first, still keeping equal items in their original order."""
    key = key or _identity
    # Compute each key once (n calls), and keep it next to its item: [key, item] pairs.
    pairs = [[key(item), item] for item in items]
    ordered = _sort(pairs, reverse)
    return [pair[1] for pair in ordered]


def _sort(pairs, reverse):
    if len(pairs) <= 1:
        return pairs
    middle = len(pairs) // 2
    left = _sort(pairs[:middle], reverse)
    right = _sort(pairs[middle:], reverse)
    return _merge(left, right, reverse)


def _comes_before(a, b, reverse):
    """Whether key `a` must come strictly before key `b`."""
    return a > b if reverse else a < b


def _merge(left, right, reverse):
    merged = []
    i = j = 0
    while i < len(left) and j < len(right):
        # Take from the right only if it is strictly first; on a tie the left wins (stable).
        if _comes_before(right[j][0], left[i][0], reverse):
            merged.append(right[j])
            j += 1
        else:
            merged.append(left[i])
            i += 1
    while i < len(left):
        merged.append(left[i])
        i += 1
    while j < len(right):
        merged.append(right[j])
        j += 1
    return merged
