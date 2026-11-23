"""
Edit distance (Levenshtein distance) and "similar title" search.

The edit distance between two strings is the smallest number of single-character edits that
turns one into the other. An edit is an insert, a delete or a substitution, and each costs 1.
For example, "cat" to "cart" is 1 (insert r), and "kitten" to "sitting" is 3.

How it works (dynamic programming):
Imagine a table where cell (i, j) holds the distance between the first i characters of `a` and
the first j characters of `b`.
- First row and column: turning a prefix into the empty string takes one delete per character.
- Any other cell: if the two current characters match, nothing new is needed, so copy the
  diagonal cell. Otherwise take the cheapest of three neighbours and add 1:
  left (insert), above (delete) or diagonal (substitute).
- The answer is the bottom-right cell.

The two-row optimisation: each cell only looks at the current row and the row above it, so
older rows are never needed again. We keep just two rows and swap them after each character.
Making the shorter string the columns keeps those rows as small as possible.

Complexity (n = len(a), m = len(b)):
- levenshtein: O(n·m) time, O(min(n, m)) space.
- similarity: O(n·m) time, O(min(n, m)) space, plus O(n + m) to normalise the text.
- find_similar: O(c·n·m + c log c) time for c candidates, O(c + min(n, m)) space.
"""

from .sorting import merge_sort


def levenshtein(a, b):
    """The minimum number of inserts, deletes and substitutions that turn `a` into `b`."""
    if len(b) > len(a):  # the shorter string becomes the columns, so the rows are short
        a, b = b, a
    previous = [0] * (len(b) + 1)
    current = [0] * (len(b) + 1)
    for j in range(len(b) + 1):
        previous[j] = j  # first row: build b[:j] from nothing with j inserts

    for i in range(1, len(a) + 1):
        current[0] = i  # first column: remove all i characters
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                current[j] = previous[j - 1]
            else:
                best = previous[j - 1]  # substitute
                if previous[j] < best:
                    best = previous[j]  # delete
                if current[j - 1] < best:
                    best = current[j - 1]  # insert
                current[j] = best + 1
        previous, current = current, previous  # this row becomes "the row above"
    return previous[len(b)]


def normalise(text):
    """Lower case, with every run of spaces collapsed to one and none at the ends."""
    return " ".join((text or "").lower().split())


def similarity(a, b):
    """How alike two texts are, from 0.0 (nothing alike) to 1.0 (the same after normalising)."""
    a, b = normalise(a), normalise(b)
    longest = len(a) if len(a) > len(b) else len(b)
    if longest == 0:
        return 1.0  # two empty texts are identical
    return 1 - levenshtein(a, b) / longest


def find_similar(title, candidates, threshold=0.6, limit=3, key=None):
    """The candidates most similar to `title`, highest first, at most `limit`.

    Only candidates with similarity >= threshold are kept. Equal scores keep their original order
    (merge sort is stable). `key(candidate)` gives the text to compare, so callers can pass
    records; by default each candidate is the text itself. A blank title matches nothing.
    """
    if not normalise(title):
        return []
    scored = []
    for candidate in candidates:
        text = key(candidate) if key else candidate
        score = similarity(title, text)
        if score >= threshold:
            scored.append([score, candidate])
    ordered = merge_sort(scored, key=lambda pair: pair[0], reverse=True)
    return [pair[1] for pair in ordered[:limit]]
