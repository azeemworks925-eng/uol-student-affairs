"""
Complaint lists, ordered and searched with the hand-written structures in dsa/ (dsa/README.md).

- sort_complaints: merge sort, for the staff lists and My Submissions.
- reference_index / find_visible: a hash table from reference to complaint ("Go to reference").
- student_trie / matching_student_ids: a trie of student names and SAP IDs (staff search).
- next_waiting: a min-heap on submission time ("Next complaint").

Privacy: every structure is built only from what the user can already see (callers pass a
queryset derived from complaints.permissions.visible_complaints), so a lookup can never
reveal anything else.
"""

from accounts.models import User
from dsa.hash_table import HashTable
from dsa.heap import MinHeap
from dsa.sorting import merge_sort
from dsa.trie import Trie

from .models import Complaint

Status = Complaint.Status

# The workflow order, defined once: used by the "Status" sort.
STATUS_ORDER = [Status.RECEIVED, Status.UNDER_REVIEW, Status.RESOLVED, Status.REJECTED]
WAITING_STATUSES = (Status.RECEIVED, Status.UNDER_REVIEW)

DEFAULT_SORT = "activity"
STUDENT_SORTS = [
    ("activity", "Latest activity"),
    ("newest", "Newest"),
    ("oldest", "Oldest"),
    ("status", "Status"),
    ("category", "Category"),
]
STAFF_SORTS = [*STUDENT_SORTS, ("cohort", "Cohort")]


def status_rank(status):
    """Position in STATUS_ORDER (unknown values last)."""
    for index, value in enumerate(STATUS_ORDER):
        if value == status:
            return index
    return len(STATUS_ORDER)


def _latest_activity(complaint):
    # Ties on the same instant are broken by the newer complaint (higher id).
    return (complaint.last_activity or complaint.created_at, complaint.pk)


def _cohort(complaint):
    return (complaint.batch.name.lower(), complaint.semester.number, complaint.section.name.lower())


def sort_complaints(complaints, sort):
    """Merge-sort the (already filtered) complaints by one of the sort options.

    Ties fall back to latest activity: merge sort is stable, so the list is first sorted by
    latest activity, then by the chosen key, and equal keys keep the latest-activity order.
    Complaints need the `last_activity` annotation. Unknown options use the default.
    """
    by_activity = merge_sort(complaints, key=_latest_activity, reverse=True)
    if sort == "newest":
        return merge_sort(complaints, key=lambda c: (c.created_at, c.pk), reverse=True)
    if sort == "oldest":
        return merge_sort(complaints, key=lambda c: (c.created_at, c.pk))
    if sort == "status":
        return merge_sort(by_activity, key=lambda c: status_rank(c.status))
    if sort == "category":
        return merge_sort(by_activity, key=lambda c: c.category.name.lower())
    if sort == "cohort":
        return merge_sort(by_activity, key=_cohort)
    return by_activity


def clean_sort(value, options):
    """The sort option if it is one of `options`, otherwise the default."""
    for option, _label in options:
        if option == value:
            return option
    return DEFAULT_SORT


# --- "Go to reference": hash table -------------------------------------------------------------

def normalise_reference(text):
    return "".join((text or "").split()).upper()


def reference_index(visible):
    """A hash table from reference to complaint, built from the visible complaints only. O(n)."""
    table = HashTable()
    for complaint in visible.select_related(None).only("pk", "reference").order_by():
        table.put(complaint.reference, complaint)
    return table


def find_visible(visible, text):
    """The visible complaint with this reference, or None. One O(1) average lookup."""
    return reference_index(visible).get(normalise_reference(text))


# --- Staff search: trie -------------------------------------------------------------------------

def student_trie(visible):
    """A trie of the students behind the visible complaints: each student's full name, each word
    of it (so a surname matches too) and their SAP ID, all pointing to the student's id."""
    trie = Trie()
    students = (User.objects.filter(pk__in=visible.order_by().values("student_id"))
                .values_list("pk", "full_name", "student_profile__sap_id").order_by())
    for pk, full_name, sap_id in students:
        name = " ".join((full_name or "").split())
        if name:
            trie.insert(name, pk)
            for word in name.split(" ")[1:]:
                trie.insert(word, pk)
        if sap_id:
            trie.insert(sap_id, pk)
    return trie


def matching_student_ids(visible, query):
    """Ids of visible students whose name, a word of their name, or SAP ID starts with the query."""
    query = " ".join((query or "").split())
    if not query:
        return []
    return student_trie(visible).starts_with(query)


# --- "Next complaint": min-heap -----------------------------------------------------------------

def next_waiting(visible):
    """The oldest complaint still Received or Under Review, or None.

    Every waiting complaint is pushed onto a min-heap keyed on (submitted at, id); the root is
    the oldest. O(n log n) to build by pushing, O(log n) to pop."""
    heap = MinHeap()
    waiting = (visible.filter(status__in=WAITING_STATUSES).select_related(None)
               .only("pk", "reference", "created_at").order_by())
    for complaint in waiting:
        heap.push((complaint.created_at, complaint.pk), complaint)
    if not len(heap):
        return None
    _priority, oldest = heap.pop()
    return oldest
