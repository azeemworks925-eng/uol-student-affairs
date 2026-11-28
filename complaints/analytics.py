"""
Super Admin Overview analytics (Complaints Part 4 Stage 4b).

Specification: docs/technical/COMPLAINTS_PART4_SPEC.md section 6. Decisions: DEC-090, DEC-205,
DEC-281, DEC-306, DEC-313, DEC-314, DEC-316, DEC-317, DEC-320 to DEC-322, and DEC-339, which
removed small-cohort suppression (it amends DEC-315, DEC-318 and DEC-319).

`build_overview(user)` returns an `Overview` for the current academic term only (DEC-316), through
`AcademicTerm.window()`; there is no all-time fallback. States:
- "setup": no current term; nothing is calculated;
- "ready": complaints per cohort, per category and by status.

Not here, by decision: a term selector or comparison (DEC-316), Batch Advisor statistics
(DEC-321), cross-tabulations of categories or statuses by cohort (spec 6.3).
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlencode

from django.db.models import Count, Q
from django.urls import reverse

from academics import services as term_services
from academics.models import Batch, Section, Semester
from accounts.models import AdvisorAssignment, StudentProfile

from .models import Complaint, ComplaintCategory
from .permissions import visible_complaints
from .presentation import status_tone
from .workspace import cohort_value

Status = Complaint.Status
NOT_RESOLVED = (Status.RECEIVED, Status.UNDER_REVIEW, Status.REJECTED)  # DEC-313
COHORT_FIELDS = ("batch_id", "semester_id", "section_id")


def percent(count, total):
    """Whole-number percentage of `total`, rounded half up; None when the total is zero."""
    if not total:
        return None
    return int((Decimal(count) * 100 / Decimal(total)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def percent_label(count, total):
    value = percent(count, total)
    if value is None:
        return ""
    if value == 0 and count:
        return "<1%"
    return f"{value}%"


def plural(count, singular, plural_form=None):
    return f"{count} {singular if count == 1 else (plural_form or singular + 's')}"


@dataclass(frozen=True)
class CohortCount:
    """One real cohort and its complaints this term."""

    short_label: str  # "DEMO-A · S4"
    label: str  # "Fall 2024 · Semester 4 · Section A"
    count: int
    url: str


@dataclass(frozen=True)
class Share:
    """A category or status line: its count, its share of the total and a list link."""

    label: str
    count: int
    percent: int | None
    percent_label: str
    url: str
    inactive: bool = False
    tone: str = ""


@dataclass(frozen=True)
class Overview:
    state: str  # "setup" or "ready"
    term: object = None
    total: int | None = None
    headline: str = ""
    cohorts: tuple = ()
    cohort_takeaway: str = ""
    categories: tuple = ()
    category_takeaway: str = ""
    resolved: Share | None = None
    not_resolved: Share | None = None
    not_resolved_parts: tuple = ()
    status_takeaway: str = ""


def _list_url(**params):
    return f"{reverse('super_admin_complaints')}?{urlencode(params)}"


def cohort_label(batch, semester, section):
    return f"{batch} · {semester} · {section}"


def _cohort_takeaway(cohorts):
    if not cohorts:
        return "No cohorts are recorded yet."
    top = max(c.count for c in cohorts)
    if top == 0:
        return "No complaints this term."
    leaders = [c.short_label for c in cohorts if c.count == top]
    if len(leaders) == 1:
        return f"Most: {leaders[0]}, {plural(top, 'complaint')}."
    return f"Most: {' and '.join(leaders[:2])}{' and others' if len(leaders) > 2 else ''}, {top} each."


def _category_takeaway(categories, total):
    if not total:
        return "No complaints this term."
    top = max(c.count for c in categories)
    leaders = [c for c in categories if c.count == top]
    if len(leaders) == 1:
        leader = leaders[0]
        return f"Largest share: {leader.label}, {plural(leader.count, 'complaint')} of {total} ({leader.percent_label})."
    names = " and ".join(c.label for c in leaders[:2]) + (" and others" if len(leaders) > 2 else "")
    return f"Largest share: {names}, {top} each of {total}."


def _status_takeaway(counts, total):
    if not total:
        return "No complaints this term."
    resolved = counts.get(Status.RESOLVED, 0)
    return f"{resolved} of {total} resolved ({percent_label(resolved, total)})."


def _grouped_counts(queryset, fields):
    """{(field values...): count}, one GROUP BY query. order_by() clears the model's default
    ordering, which would otherwise be added to the GROUP BY and split the groups."""
    rows = queryset.order_by().values(*fields).annotate(n=Count("pk"))
    return {tuple(row[f] for f in fields): row["n"] for row in rows}


def _cohorts(in_window, term):
    """Every real cohort (DEC-317: assignments, profiles and complaints in the window), in
    academic order, with its complaints this term."""
    by_cohort = _grouped_counts(in_window, COHORT_FIELDS)
    keys = set(AdvisorAssignment.objects.order_by().values_list(*COHORT_FIELDS).distinct())
    keys |= set(StudentProfile.objects.order_by().values_list(*COHORT_FIELDS).distinct())
    keys |= set(by_cohort)
    batches = Batch.objects.in_bulk({k[0] for k in keys})
    semesters = Semester.objects.in_bulk({k[1] for k in keys})
    sections = Section.objects.in_bulk({k[2] for k in keys})

    def academic(key):
        b, s, c = batches[key[0]], semesters[key[1]], sections[key[2]]
        return (s.number, b.name, b.pk, c.name, c.pk)

    return tuple(
        CohortCount(
            short_label=f"{sections[key[2]].name} · S{semesters[key[1]].number}",
            label=cohort_label(batches[key[0]], semesters[key[1]], sections[key[2]]),
            count=by_cohort.get(key, 0),
            url=_list_url(cohort=cohort_value(*key), term=term.pk),
        )
        for key in sorted(keys, key=academic)
    )


def build_overview(user):
    """The analytics for the Super Admin Overview."""
    term = term_services.current_term()
    if term is None:
        return Overview(state="setup")  # DEC-316: never an all-time fallback

    start, end = term.window()
    in_window = visible_complaints(user).filter(created_at__gte=start, created_at__lt=end).order_by()
    by_status = {key[0]: n for key, n in _grouped_counts(in_window, ("status",)).items()}
    total = sum(by_status.values())
    cohorts = _cohorts(in_window, term)

    # Categories (DEC-321): every active category, and inactive ones only with complaints.
    by_category = {key[0]: n for key, n in _grouped_counts(in_window, ("category_id",)).items()}
    categories = tuple(
        Share(
            label=category.name, count=by_category.get(category.pk, 0),
            percent=percent(by_category.get(category.pk, 0), total),
            percent_label=percent_label(by_category.get(category.pk, 0), total),
            url=_list_url(category=category.pk, term=term.pk), inactive=not category.is_active,
        )
        for category in ComplaintCategory.objects.filter(Q(is_active=True) | Q(pk__in=by_category))
    )

    # Resolved versus not resolved (DEC-313).
    def status_share(status, label):
        count = by_status.get(status, 0)
        return Share(label=label, count=count, percent=percent(count, total), percent_label=percent_label(count, total),
                     url=_list_url(status=status, term=term.pk), tone=status_tone(status))
    not_resolved_count = sum(by_status.get(s, 0) for s in NOT_RESOLVED)

    return Overview(
        state="ready",
        term=term,
        total=total,
        headline=f"{plural(total, 'complaint')} in {term.name}." if total else f"No complaints in {term.name} yet.",
        cohorts=cohorts,
        cohort_takeaway=_cohort_takeaway(cohorts),
        categories=categories,
        category_takeaway=_category_takeaway(categories, total),
        resolved=status_share(Status.RESOLVED, "Resolved"),
        not_resolved=Share(label="Not resolved", count=not_resolved_count, percent=percent(not_resolved_count, total),
                           percent_label=percent_label(not_resolved_count, total), url=""),
        not_resolved_parts=(
            status_share(Status.RECEIVED, "Received"),
            status_share(Status.UNDER_REVIEW, "Under review"),
            status_share(Status.REJECTED, "Rejected"),
        ),
        status_takeaway=_status_takeaway(by_status, total),
    )
