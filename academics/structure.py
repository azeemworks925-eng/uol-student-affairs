"""
Read-only figures for the people and structure pages: per-cohort counts and the department tree.

A real cohort is one that has a student profile, an advisor assignment or a complaint (DEC-317).
These are operational figures for the Super Admin, whose access to individual records is not
limited by the analytics suppression rules (DEC-320, DEC-330).
"""

from django.db.models import Count

from accounts.models import AdvisorAssignment, StudentProfile
from complaints.models import Complaint, ComplaintStatus
from dsa.tree import CohortRow, build_department_tree, dfs_totals

from .models import Batch, Section, Semester

COHORT_FIELDS = ("batch_id", "semester_id", "section_id")
OPEN_COMPLAINTS = (ComplaintStatus.RECEIVED, ComplaintStatus.UNDER_REVIEW)


def cohort_counts():
    """{(batch_id, semester_id, section_id): {"students", "active", "open"}} for every real cohort."""
    counts = {}

    def entry(key):
        return counts.setdefault(key, {"students": 0, "active": 0, "open": 0})

    rows = (StudentProfile.objects.order_by().values_list(*COHORT_FIELDS, "user__is_active")
            .annotate(total=Count("pk")))
    for batch_id, semester_id, section_id, is_active, total in rows:
        item = entry((batch_id, semester_id, section_id))
        item["students"] += total
        if is_active:
            item["active"] += total
    for key in AdvisorAssignment.objects.order_by().values_list(*COHORT_FIELDS).distinct():
        entry(tuple(key))
    for key in Complaint.objects.order_by().values_list(*COHORT_FIELDS).distinct():
        entry(tuple(key))
    open_rows = (Complaint.objects.filter(status__in=OPEN_COMPLAINTS).order_by()
                 .values_list(*COHORT_FIELDS).annotate(total=Count("pk")))
    for batch_id, semester_id, section_id, total in open_rows:
        entry((batch_id, semester_id, section_id))["open"] = total
    return counts


def department_outline():
    """The department tree's root entry with DFS totals, each node marked if its entry is inactive."""
    batches = Batch.objects.in_bulk()
    semesters = Semester.objects.in_bulk()
    sections = Section.objects.in_bulk()
    rows = [
        CohortRow(batches[b].name, semesters[s].number, sections[c].name,
                  item["students"], item["active"], item["open"])
        for (b, s, c), item in cohort_counts().items()
    ]
    root = build_department_tree(rows, StudentProfile.DEFAULT_DEPARTMENT)
    inactive = (
        (),
        tuple(batch.name for batch in batches.values() if not batch.is_active),
        tuple(f"Semester {semester.number}" for semester in semesters.values() if not semester.is_active),
        tuple(f"Section {section.name}" for section in sections.values() if not section.is_active),
    )
    entries = dfs_totals(root)
    for entry in entries:
        entry.inactive = entry.label in inactive[entry.depth]
    return entries[0], len(rows)
