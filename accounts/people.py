"""
Read-only data for the Super Admin's People pages (DEC-330). Nothing here writes: every change
goes through accounts.services.

Search uses the hand-written trie and every ordering uses merge sort (dsa/README.md).
"""

from dataclasses import dataclass

from allauth.socialaccount.models import SocialAccount
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from academics.structure import OPEN_COMPLAINTS, cohort_counts
from complaints.models import Complaint, ComplaintEvent
from dsa.sorting import merge_sort
from dsa.trie import Trie
from meetings.models import Meeting, MeetingEvent
from voice.models import Submission

from . import identity
from .models import AdvisorAssignment, CohortRepresentation, User

STUDENT_SORTS = [("", "Name"), ("sap", "SAP ID"), ("cohort", "Cohort"), ("newest", "Newest registered")]
STUDENT_STATUSES = [("", "All"), ("active", "Active"), ("inactive", "Inactive"), ("rep", "CR/GR"),
                    ("unregistered", "Not registered")]
STAFF_STATUSES = [("", "All"), ("active", "Active"), ("inactive", "Inactive")]
STAFF_SORTS = [("", "Name"), ("email", "Email"), ("newest", "Newest")]


def current_posts():
    """{user id: "CR" or "GR"} for every current representative."""
    posts = {}
    for cr_id, gr_id in CohortRepresentation.objects.current().order_by().values_list("cr_id", "gr_id"):
        posts[cr_id] = "CR"
        posts[gr_id] = "GR"
    return posts


# --- Students ------------------------------------------------------------------------------------

@dataclass
class StudentRow:
    user: User
    profile: object
    name: str
    sap_id: str
    post: str
    is_active: bool
    registered: object

    @property
    def cohort_key(self):
        if self.profile is None:
            return ("", 0, "")
        return (self.profile.batch.name, self.profile.semester.number, self.profile.section.name)


def student_rows():
    users = User.objects.filter(role=User.Role.STUDENT).order_by().select_related(
        "student_profile__batch", "student_profile__semester", "student_profile__section")
    posts = current_posts()
    rows = []
    for user in users:
        profile = getattr(user, "student_profile", None)
        rows.append(StudentRow(
            user=user, profile=profile, name=user.get_full_name(),
            sap_id=profile.sap_id if profile else (identity.extract_sap_id(user.email) or ""),
            post=posts.get(user.pk, ""), is_active=user.is_active,
            registered=profile.created_at if profile else None,
        ))
    return rows


def student_stats(rows):
    active = sum(1 for row in rows if row.is_active)
    return [
        {"value": len(rows), "label": "Total", "icon": "users"},
        {"value": active, "label": "Active", "icon": "check", "tone": "resolved"},
        {"value": sum(1 for row in rows if row.post), "label": "CR/GR", "icon": "badge"},
        {"value": len(rows) - active, "label": "Inactive", "icon": "clock"},
    ]


def search_students(rows, query):
    """Rows whose full name, a word of their name, or SAP ID starts with the query (trie)."""
    query = " ".join((query or "").split())
    if not query:
        return rows
    trie = Trie()
    for row in rows:
        name = " ".join((row.user.full_name or "").split())
        if name:
            trie.insert(name, row.user.pk)
            for word in name.split(" ")[1:]:
                trie.insert(word, row.user.pk)
        if row.sap_id:
            trie.insert(row.sap_id, row.user.pk)
    found = set(trie.starts_with(query))
    return [row for row in rows if row.user.pk in found]


def filter_students(rows, *, batch="", semester="", section="", status=""):
    def keep(row):
        profile = row.profile
        if batch and (profile is None or str(profile.batch_id) != batch):
            return False
        if semester and (profile is None or str(profile.semester_id) != semester):
            return False
        if section and (profile is None or str(profile.section_id) != section):
            return False
        return {"": True, "active": row.is_active, "inactive": not row.is_active,
                "rep": bool(row.post), "unregistered": profile is None}.get(status, True)

    return [row for row in rows if keep(row)]


def sort_students(rows, sort):
    """Stable: sorted by name first, then by the chosen key."""
    ordered = merge_sort(rows, key=lambda row: (row.name.casefold(), row.user.pk))
    if sort == "sap":
        return merge_sort(ordered, key=lambda row: row.sap_id)
    if sort == "cohort":
        return merge_sort(ordered, key=lambda row: row.cohort_key)
    if sort == "newest":
        return merge_sort(ordered, key=lambda row: row.registered.timestamp() if row.registered else 0, reverse=True)
    return ordered


def student_activity(user, sap_id):
    """The student's record counts, each with a link the Super Admin can already open."""
    complaints = Complaint.objects.filter(student=user)
    voice = Submission.objects.filter(student=user)
    meetings = Meeting.objects.filter(student=user)
    search = f"?q={sap_id}" if sap_id else ""
    latest_meeting = meetings.order_by("-created_at", "-pk").values_list("pk", flat=True).first()
    return [
        {"label": "Complaints", "value": complaints.count(), "icon": "file",
         "detail": f"{complaints.filter(status__in=OPEN_COMPLAINTS).count()} open",
         "url": reverse("super_admin_complaints") + search if search else ""},
        {"label": "Student Voice", "value": voice.count(), "icon": "voice",
         "detail": f"{voice.filter(status=Submission.Status.WAITING).count()} waiting",
         "url": reverse("super_admin_voice") + search if search else ""},
        {"label": "Meetings", "value": meetings.count(), "icon": "calendar",
         "detail": f"{meetings.filter(status=Meeting.Status.CONFIRMED).count()} confirmed",
         "url": reverse("super_admin_meeting_detail", args=[latest_meeting]) if latest_meeting else "",
         "link_label": "Latest meeting"},
    ]


def google_linked(user):
    return SocialAccount.objects.filter(user=user).exists()


# --- Staff ---------------------------------------------------------------------------------------

@dataclass
class StaffRow:
    user: User
    name: str
    email: str
    is_active: bool
    cohorts: int
    linked: bool


def staff_rows(role):
    users = list(User.objects.filter(role=role).order_by().annotate(cohort_total=Count("advisor_assignments")))
    linked = set(SocialAccount.objects.filter(user__role=role).values_list("user_id", flat=True))
    return [StaffRow(user=user, name=user.get_full_name(), email=user.email, is_active=user.is_active,
                     cohorts=user.cohort_total, linked=user.pk in linked) for user in users]


def filter_staff(rows, *, query="", status=""):
    needle = " ".join((query or "").split()).casefold()

    def keep(row):
        if needle and needle not in row.name.casefold() and needle not in row.email:
            return False
        return {"": True, "active": row.is_active, "inactive": not row.is_active}.get(status, True)

    return [row for row in rows if keep(row)]


def sort_staff(rows, sort):
    ordered = merge_sort(rows, key=lambda row: (row.name.casefold(), row.user.pk))
    if sort == "email":
        return merge_sort(ordered, key=lambda row: row.email)
    if sort == "newest":
        return merge_sort(ordered, key=lambda row: row.user.date_joined.timestamp(), reverse=True)
    return ordered


def coverage():
    """Which active cohorts have an active advisor: (covered keys, uncovered keys)."""
    from academics.models import Batch, Section, Semester

    active_batches = set(Batch.objects.active().values_list("pk", flat=True))
    active_semesters = set(Semester.objects.active().values_list("pk", flat=True))
    active_sections = set(Section.objects.active().values_list("pk", flat=True))
    known = {key for key in cohort_counts()
             if key[0] in active_batches and key[1] in active_semesters and key[2] in active_sections}
    assigned = set(AdvisorAssignment.objects.filter(advisor__is_active=True).order_by()
                   .values_list("batch_id", "semester_id", "section_id"))
    return known & assigned, known - assigned


def cohorts_left_uncovered(advisor):
    """Active cohorts that only this advisor covers, so deactivating them leaves no advisor."""
    own = list(AdvisorAssignment.objects.filter(advisor=advisor).select_related("batch", "semester", "section"))
    others = set(AdvisorAssignment.objects.filter(advisor__is_active=True).exclude(advisor=advisor).order_by()
                 .values_list("batch_id", "semester_id", "section_id"))
    return [a for a in own if (a.batch_id, a.semester_id, a.section_id) not in others
            and a.batch.is_active and a.semester.is_active and a.section.is_active]


def owned_open_complaints(advisor, assignment=None):
    """Open complaints naming this advisor as responsible owner (in one cohort, if given)."""
    complaints = Complaint.objects.filter(responsible=advisor, status__in=OPEN_COMPLAINTS)
    if assignment is not None:
        complaints = complaints.filter(batch_id=assignment.batch_id, semester_id=assignment.semester_id,
                                       section_id=assignment.section_id)
    return complaints.count()


def advisor_assignments(advisor):
    """The advisor's assignments with each cohort's figures, in academic order."""
    counts = cohort_counts()
    others = set(AdvisorAssignment.objects.filter(advisor__is_active=True).exclude(advisor=advisor).order_by()
                 .values_list("batch_id", "semester_id", "section_id"))
    rows = list(AdvisorAssignment.objects.filter(advisor=advisor).select_related("batch", "semester", "section", "assigned_by"))
    for row in rows:
        key = (row.batch_id, row.semester_id, row.section_id)
        figures = counts.get(key, {"students": 0, "active": 0, "open": 0})
        row.students = figures["students"]
        row.open_complaints = figures["open"]
        row.only_advisor = key not in others
        row.is_active_cohort = row.batch.is_active and row.semester.is_active and row.section.is_active
        row.owned_open = owned_open_complaints(advisor, row)
    return merge_sort(rows, key=lambda r: (r.batch.name, r.semester.number, r.section.name))


def advisor_coverage(advisor, assignments):
    open_total = sum(row.open_complaints for row in assignments)
    upcoming = Meeting.objects.filter(advisor=advisor, status=Meeting.Status.CONFIRMED,
                                      starts_at__gte=timezone.now()).count()
    return {"cohorts": len(assignments), "open": open_total, "upcoming": upcoming}


def advisor_activity(advisor, limit=10):
    """The advisor's latest responses, status changes, Student Voice replies and meeting steps."""
    name = advisor.get_full_name()
    items = []
    events = (ComplaintEvent.objects.filter(actor=advisor, kind__in=[ComplaintEvent.Kind.RESPONSE, ComplaintEvent.Kind.STATUS_CHANGED])
              .select_related("complaint").order_by("-created_at", "-pk")[:limit])
    for event in events:
        reference = event.complaint.reference
        what = (f"responded on {reference}" if event.kind == ComplaintEvent.Kind.RESPONSE
                else f"moved {reference} to {event.get_to_status_display()}")
        items.append({"who": name, "what": what, "when": event.created_at,
                      "url": reverse("super_admin_complaint_detail", args=[reference])})
    for submission in Submission.objects.filter(answered_by=advisor).order_by("-answered_at", "-pk")[:limit]:
        items.append({"who": name, "what": "answered a Student Voice submission", "when": submission.answered_at,
                      "url": reverse("super_admin_voice_detail", args=[submission.pk])})
    reviewed = Submission.objects.filter(reviewed_by=advisor, reviewed_at__isnull=False)
    for submission in reviewed.order_by("-reviewed_at", "-pk")[:limit]:
        items.append({"who": name, "what": "reviewed a Student Voice submission", "when": submission.reviewed_at,
                      "url": reverse("super_admin_voice_detail", args=[submission.pk])})
    steps = MeetingEvent.objects.filter(actor=advisor).order_by("-created_at", "-pk")[:limit]
    for step in steps:
        items.append({"who": name, "what": f"meeting: {step.get_kind_display().lower()}", "when": step.created_at,
                      "url": reverse("super_admin_meeting_detail", args=[step.meeting_id])})
    return merge_sort(items, key=lambda item: item["when"], reverse=True)[:limit]
