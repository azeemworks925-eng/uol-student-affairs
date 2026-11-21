# dsa: hand-written data structures and algorithms

This package holds the data structures and algorithms that the portal implements by hand
(4th-semester DSA course project). Each one is used inside a real feature, and is not a
separate demo.

## Rules

- `dsa/` is a plain Python package, not a Django app: it has no models and no migrations.
- The core logic does not use `sorted()`, `list.sort()`, `heapq`, `bisect`, `collections`,
  `dict` or `set`. Python lists are used only as plain arrays.
- Every module starts with a plain-language explanation of how it works. It also states the
  time and space complexity of each public operation.
- `dsa/tests/` checks edge cases, plus 200 random cases per structure against a Python
  built-in used as the oracle. The tests may use built-ins; the structures may not.
- Callers build each structure only from data the user is already allowed to see. The query
  is derived from `complaints.permissions.visible_complaints`, so the structures cannot leak
  anything new.

## Structures

| Structure | File | Where it is used | Complexity |
|---|---|---|---|
| Merge sort (stable) | `sorting.py` | Complaint lists: the Batch Advisor and Super Admin workspaces, and the student's My Submissions. Sort options: Latest activity, Newest, Oldest, Status, Category, Cohort. Also the Student Home "Your latest updates" list. | Time O(n log n) in every case; space O(n) |
| Hash table (separate chaining) | `hash_table.py` | "Go to reference" in both staff workspaces: a table from reference to complaint | `put`/`get`/`contains`: O(k) average, O(k + n) worst; resize O(n), amortised O(1) per put; `len`: O(1); space O(n) |
| Trie (prefix tree) | `trie.py` | The staff workspace search: student names, each word of a name, and SAP IDs, by prefix | `insert`: O(L·s); `starts_with`: O(L·s + m); space O(total characters) |
| Binary min-heap | `heap.py` | "Next complaint" (Batch Advisor): the oldest complaint still Received or Under Review | `push`/`pop`: O(log n); `peek`/`len`: O(1); space O(n) |

The variables in the table are:
- *n*: the number of items;
- *k*: the key length;
- *L*: the length of the word or prefix;
- *s*: the children per trie node (at most the alphabet);
- *m*: the nodes under a matched prefix.

## How each one is wired

All four are wired through `complaints/ordering.py`.

- **Merge sort:** `sort_complaints` merge-sorts the filtered list in Python before it is paginated.
  - The database only filters; it does not order the rows.
  - Ties fall back to latest activity, using stability: the list is sorted by latest activity
    first, then by the chosen key.
  - The status order is the workflow order, defined once in `STATUS_ORDER`.
- **Hash table:** `reference_index` / `find_visible` build the table from the user's visible
  complaints (O(n)). Then they look the typed reference up once (O(1) on average).
  - In production, a database index on `reference` would do this job. The table makes the
    data structure visible for the course.
- **Trie:** `student_trie` / `matching_student_ids` build the trie from the students behind the
  visible complaints. The search shows complaints whose reference contains the query, or
  whose student matches it by prefix. For the Super Admin, a matching title also counts.
- **Min-heap:** `next_waiting` pushes every waiting complaint with the priority
  (submitted at, id), then pops the root, which is the oldest.
