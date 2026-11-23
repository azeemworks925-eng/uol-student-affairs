"""
Interval overlap detection.

An interval is a tuple (start, end, label). It covers start up to, but not including, end, so a
meeting ending at 10:30 does not overlap one starting at 10:30.

How find_overlaps works:
1. Sort: merge-sort the intervals by start time.
2. Sweep: walk through them once, remembering the interval with the latest end seen so far. If
   the current interval starts before that end, the two overlap, so record the pair. Then, if
   the current interval ends later, it becomes the new "latest end".

Why one comparison is enough: after sorting, everything earlier started no later than the current
interval. So the current interval overlaps something earlier exactly when it starts before the
latest end. Every interval that overlaps an earlier one is reported once, paired with the interval
holding the latest end. Other pairs inside a crowded group are not listed: listing all of them
could take O(n^2), because n intervals can form n(n-1)/2 pairs.

overlaps_with answers the question the portal needs: "which intervals overlap this one?" It runs
the sweep, keeps the pairs containing the target, removes those intervals and sweeps again, until
a sweep finds nothing new.

Complexity (n = number of intervals, k = intervals overlapping the target):
- find_overlaps: time O(n log n) (sort O(n log n) + sweep O(n)); space O(n).
- overlaps_with: time O((k + 1) * n log n); space O(n).
"""

from .sorting import merge_sort


def _start(interval):
    return interval[0]


def find_overlaps(intervals):
    """Return (earlier, later) pairs from one sweep over the intervals sorted by start.
    Raises ValueError if an interval does not end after it starts."""
    ordered = merge_sort(intervals, key=_start)
    pairs = []
    latest = None  # the interval with the latest end seen so far
    for current in ordered:
        if current[1] <= current[0]:
            raise ValueError("An interval must end after it starts.")
        if latest is not None and current[0] < latest[1]:
            pairs.append((latest, current))
        if latest is None or current[1] > latest[1]:
            latest = current
    return pairs


def _contains(items, wanted):
    for item in items:
        if item is wanted:
            return True
    return False


def overlaps_with(target, intervals):
    """Return every interval that overlaps `target`, ordered by start time."""
    remaining = [interval for interval in intervals if interval is not target]
    found = []
    while True:
        hits = []
        for earlier, later in find_overlaps([target, *remaining]):
            if earlier is target:
                hits.append(later)
            elif later is target:
                hits.append(earlier)
        if not hits:
            return merge_sort(found, key=_start)
        found.extend(hits)
        remaining = [interval for interval in remaining if not _contains(hits, interval)]
