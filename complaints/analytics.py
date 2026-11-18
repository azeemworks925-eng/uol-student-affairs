"""
Super Admin Overview analytics (Complaints Part 4 Stage 4b).

Specification: docs/technical/COMPLAINTS_PART4_SPEC.md section 6. Decisions: DEC-090, DEC-205,
DEC-281, DEC-306, DEC-313 to DEC-322.

`build_overview(user)` returns an `Overview` holding **only values that may be displayed**.
Suppression is decided here, before anything reaches a template: a suppressed cohort's count is
never stored on the returned objects, so it cannot leak into HTML, links, attributes or context.

Reporting window: the current academic term only (DEC-316), through `AcademicTerm.window()`;
there is no all-time fallback. States:
- "setup": no current term; nothing is calculated;
- "withheld": DEC-319, the same for both of its cases; only the term is returned;
- "ready": the three analytics.

Privacy (DEC-315, DEC-318, DEC-319). The observer of the page knows every visible cohort cell
and the department total T (printed, and also the sum of the category counts and of the status
counts), and that counts are whole numbers of at least zero. A cohort that is real only
because complaints were submitted in it this term (no student profile, no advisor assignment)
is also known to have at least one complaint: its presence on the map says so. The only
displayed equation over the hidden cohort values is that they add up to T minus the visible
cells. A hidden value is safe when more than one value for it is consistent with all of that
(the uniqueness test of spec 6.4), which for one equation means at least two hidden cells whose
combined total exceeds the sum of their known lower bounds by at least one. `plan_suppression` chooses the hidden set; `determined_keys` is the general
uniqueness check it is verified against before anything is shown.

Not here, by decision: a term selector or comparison (DEC-316), Batch Advisor statistics
(DEC-321), cross-tabulations of categories or statuses by cohort (spec 6.3). This module limits
nothing in the operational complaint list (DEC-320).
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from itertools import product
from urllib.parse import urlencode

from django.db.models import Count, Q
from django.urls import reverse

from academics import services as term_services
from academics.models import Batch, Section, Semester
from accounts.models import AdvisorAssignment, StudentProfile, User

from .models import Complaint, ComplaintCategory
from .permissions import visible_complaints
from .presentation import status_tone
from .workspace import cohort_value

MIN_ACTIVE_STUDENTS = 5  # DEC-315
Status = Complaint.Status
NOT_RESOLVED = (Status.RECEIVED, Status.UNDER_REVIEW, Status.REJECTED)  # DEC-313
COHORT_FIELDS = ("batch_id", "semester_id", "section_id")
ENUMERATION_LIMIT = 200_000  # beyond this, the general uniqueness check answers "unsafe"


# ---------------------------------------------------------------------------------------------
# Suppression (pure functions, no database access)
# ---------------------------------------------------------------------------------------------

def determined_keys(hidden_counts, equations, lower_bounds=None):
    """The hidden keys whose value an observer can determine uniquely.

    `hidden_counts` maps each hidden key to its true count. `equations` lists sets of hidden keys
    whose combined total the observer can infer from the page. `lower_bounds` maps keys to a
    minimum the observer knows (default 0; for example 1 for a cohort that appears only because
    of its complaints). A key that appears in no equation is unconstrained, so it is never
    determined.

    Disjoint equations have an exact answer: a group is safe when it has at least two keys and
    its total exceeds the sum of their lower bounds by at least one (every key can then take its
    lower bound or more). Overlapping equations are checked by exhaustive enumeration; if that
    would be too large, every constrained key is reported as determined, so the caller withholds.
    """
    lower = lower_bounds or {}
    equations = [frozenset(keys) for keys in equations if keys]
    constrained = set().union(*equations) if equations else set()
    disjoint = sum(len(keys) for keys in equations) == len(constrained)
    if disjoint:
        determined = set()
        for keys in equations:
            slack = sum(hidden_counts[k] - lower.get(k, 0) for k in keys)
            if len(keys) < 2 or slack == 0:
                determined |= keys
        return determined

    keys = sorted(constrained, key=repr)
    totals = [(eq, sum(hidden_counts[k] for k in eq)) for eq in equations]
    bounds = {k: (lower.get(k, 0), min(total for eq, total in totals if k in eq)) for k in keys}
    size = 1
    for k in keys:
        size *= max(bounds[k][1] - bounds[k][0] + 1, 1)
        if size > ENUMERATION_LIMIT:
            return set(keys)  # fail closed
    seen = {k: set() for k in keys}
    for values in product(*(range(bounds[k][0], bounds[k][1] + 1) for k in keys)):
        assignment = dict(zip(keys, values))
        if all(sum(assignment[k] for k in eq) == total for eq, total in totals):
            for k in keys:
                seen[k].add(assignment[k])
    return {k for k in keys if len(seen[k]) <= 1}


def plan_suppression(cells, order, lower_bounds=None):
    """Choose the cohort cells to hide (DEC-315, DEC-318, DEC-319).

    `cells` maps each real cohort key to `(complaints, active_students)`. `order` is the stable
    preference for complementary cells (every key, most preferred first): it does not depend on
    complaint counts, so the same complement is chosen while it stays usable. `lower_bounds`
    maps keys to the minimum the observer knows (see `determined_keys`).

    Returns the frozenset of hidden keys, or None when the analytics must be withheld:
    (a) the total is zero and a cohort needs primary suppression, or (b) no complementary
    arrangement makes every hidden value safe.
    """
    lower = lower_bounds or {}
    primary = {key for key, (_, students) in cells.items() if students < MIN_ACTIVE_STUDENTS}
    if not primary:
        return frozenset()
    total = sum(count for count, _ in cells.values())
    if total == 0:
        return None  # DEC-319 (a)

    def slack(key):
        return cells[key][0] - lower.get(key, 0)

    hidden = set(primary)
    candidates = [key for key in order if key in cells and key not in hidden]
    if sum(slack(key) for key in hidden) == 0:
        # Every hidden cell would be known to sit at its lower bound (for example, cells adding
        # up to zero): add the first preferred cell with complaints above its own lower bound.
        complement = next((key for key in candidates if slack(key) > 0), None)
        if complement is None:
            return None  # DEC-319 (b): no arrangement can be safe
        hidden.add(complement)
    elif len(hidden) == 1:
        if not candidates:
            return None  # DEC-319 (b): the only real cohort is suppressed
        hidden.add(candidates[0])

    hidden_counts = {key: cells[key][0] for key in hidden}
    if determined_keys(hidden_counts, [hidden], lower):
        return None  # defensive: never show an arrangement that fails the uniqueness test
    return frozenset(hidden)


# ---------------------------------------------------------------------------------------------
# Displayed values
# ---------------------------------------------------------------------------------------------

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
class CohortCell:
    """One grid position. `count` and `url` are set only for a visible real cohort."""

    section: str
    state: str  # "count", "zero", "hidden" or "none" (not a real cohort)
    label: str  # "Fall 2024 · Semester 4 · Section A"
    count: int | None = None
    url: str | None = None


@dataclass(frozen=True)
class CohortRow:
    semester: str
    batch: str
    cells: tuple


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
    state: str  # "setup", "withheld" or "ready"
    term: object = None
    total: int | None = None
    headline: str = ""
    sections: tuple = ()
    rows: tuple = ()
    hidden_cells: int = 0
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


def _cohort_takeaway(visible_counts, hidden_cells, total):
    """Written from visible cells only: a suppressed cohort is never named, ranked or compared."""
    if not visible_counts and hidden_cells:
        return "Every cohort is hidden for privacy, so this term's distribution is not shown by cohort."
    if not visible_counts:
        return "No cohorts are recorded yet."
    scope = "among the cohorts shown" if hidden_cells else "across the department"
    top = max(visible_counts.values())
    if top == 0:
        return f"No complaints were submitted {scope} this term."
    leaders = [label for label, count in visible_counts.items() if count == top]
    if len(leaders) == 1:
        return f"{leaders[0]} has the most complaints {scope}: {plural(top, 'complaint')}."
    return f"{' and '.join(leaders[:2])}{' and others' if len(leaders) > 2 else ''} have the most complaints {scope}: {top} each."


def _category_takeaway(categories, total):
    if not total:
        return "No complaints were submitted this term, so no category stands out."
    top = max(c.count for c in categories)
    leaders = [c for c in categories if c.count == top]
    if len(leaders) == 1:
        leader = leaders[0]
        return f"{leader.label} accounts for the largest share: {plural(leader.count, 'complaint')} of {total} ({leader.percent_label})."
    names = " and ".join(c.label for c in leaders[:2]) + (" and others" if len(leaders) > 2 else "")
    return f"{names} share the largest number of complaints: {top} each of {total}."


def _status_takeaway(counts, total):
    if not total:
        return "No complaints were submitted this term."
    resolved = counts.get(Status.RESOLVED, 0)
    handling = counts.get(Status.RECEIVED, 0) + counts.get(Status.UNDER_REVIEW, 0)
    rejected = counts.get(Status.REJECTED, 0)
    not_resolved = handling + rejected
    first = f"{resolved} of {total} {'is' if resolved == 1 else 'are'} resolved ({percent_label(resolved, total)})."
    if not not_resolved:
        return first + " None are unresolved."
    parts = []
    if handling:
        parts.append(f"{handling} {'is' if handling == 1 else 'are'} still being handled")
    if rejected:
        parts.append(f"{rejected} {'was' if rejected == 1 else 'were'} rejected")
    return f"{first} {not_resolved} {'is' if not_resolved == 1 else 'are'} not resolved: {' and '.join(parts)}."


# ---------------------------------------------------------------------------------------------
# Building the Overview
# ---------------------------------------------------------------------------------------------

def _grouped_counts(queryset, fields):
    """{(field values...): count}, one GROUP BY query. order_by() clears the model's default
    ordering, which would otherwise be added to the GROUP BY and split the groups."""
    rows = queryset.order_by().values(*fields).annotate(n=Count("pk"))
    return {tuple(row[f] for f in fields): row["n"] for row in rows}


def build_overview(user):
    """The analytics for the Super Admin Overview, with only displayable values."""
    term = term_services.current_term()
    if term is None:
        return Overview(state="setup")  # DEC-316: never an all-time fallback

    start, end = term.window()
    in_window = visible_complaints(user).filter(created_at__gte=start, created_at__lt=end).order_by()
    by_cohort = _grouped_counts(in_window, COHORT_FIELDS)
    total = sum(by_cohort.values())

    # Real cohorts (DEC-317): assignments, profiles and complaints in the window.
    structural = set(AdvisorAssignment.objects.order_by().values_list(*COHORT_FIELDS).distinct())
    structural |= set(StudentProfile.objects.order_by().values_list(*COHORT_FIELDS).distinct())
    universe = structural | set(by_cohort)
    # A cohort real only through this term's complaints shows that it has at least one.
    lower_bounds = {key: 1 for key in universe - structural}
    students = _grouped_counts(
        StudentProfile.objects.filter(user__is_active=True, user__role=User.Role.STUDENT), COHORT_FIELDS
    )

    batches = Batch.objects.in_bulk({k[0] for k in universe})
    semesters = Semester.objects.in_bulk({k[1] for k in universe})
    sections = Section.objects.in_bulk({k[2] for k in universe})

    def academic(key):
        b, s, c = batches[key[0]], semesters[key[1]], sections[key[2]]
        return (s.number, b.name, b.pk, c.name, c.pk)

    cells = {key: (by_cohort.get(key, 0), students.get(key, 0)) for key in universe}
    # Complement preference: the largest cohorts by active students first, then academic order.
    # It does not depend on complaint counts, so it is stable between visits (spec 6.4).
    order = sorted(universe, key=lambda key: (-cells[key][1], academic(key)))
    hidden = plan_suppression(cells, order, lower_bounds)
    if hidden is None:
        return Overview(state="withheld", term=term)  # DEC-319: the same for both cases

    term_param = term.pk
    # Grid (DEC-306, DEC-321): rows are semester + batch in academic order, columns are sections.
    row_keys = sorted({(k[1], k[0]) for k in universe}, key=lambda rk: (semesters[rk[0]].number, batches[rk[1]].name, rk[1]))
    column_ids = sorted({k[2] for k in universe}, key=lambda c: (sections[c].name, c))
    rows, visible_counts = [], {}
    for semester_id, batch_id in row_keys:
        row_cells = []
        for section_id in column_ids:
            key = (batch_id, semester_id, section_id)
            label = cohort_label(batches[batch_id], semesters[semester_id], sections[section_id])
            section_label = str(sections[section_id])
            if key not in universe:
                row_cells.append(CohortCell(section=section_label, state="none", label=label))
            elif key in hidden:
                row_cells.append(CohortCell(section=section_label, state="hidden", label=label))
            else:
                count = cells[key][0]
                visible_counts[label] = count
                row_cells.append(CohortCell(
                    section=section_label, state="count" if count else "zero", label=label, count=count,
                    url=_list_url(cohort=cohort_value(*key), term=term_param),
                ))
        rows.append(CohortRow(semester=str(semesters[semester_id]), batch=str(batches[batch_id]), cells=tuple(row_cells)))

    # Categories (DEC-321): every active category, and inactive ones only with complaints.
    by_category = {key[0]: n for key, n in _grouped_counts(in_window, ("category_id",)).items()}
    categories = tuple(
        Share(
            label=category.name, count=by_category.get(category.pk, 0),
            percent=percent(by_category.get(category.pk, 0), total),
            percent_label=percent_label(by_category.get(category.pk, 0), total),
            url=_list_url(category=category.pk, term=term_param), inactive=not category.is_active,
        )
        for category in ComplaintCategory.objects.filter(Q(is_active=True) | Q(pk__in=by_category))
    )

    # Resolved versus not resolved (DEC-313).
    by_status = {key[0]: n for key, n in _grouped_counts(in_window, ("status",)).items()}
    def status_share(status, label):
        count = by_status.get(status, 0)
        return Share(label=label, count=count, percent=percent(count, total), percent_label=percent_label(count, total),
                     url=_list_url(status=status, term=term_param), tone=status_tone(status))
    not_resolved_count = sum(by_status.get(s, 0) for s in NOT_RESOLVED)

    return Overview(
        state="ready",
        term=term,
        total=total,
        headline=(
            f"{plural(total, 'complaint')} {'was' if total == 1 else 'were'} submitted in {term.name}."
            if total else f"No complaints have been submitted in {term.name}."
        ),
        sections=tuple(str(sections[c]) for c in column_ids),
        rows=tuple(rows),
        hidden_cells=len(hidden),
        cohort_takeaway=_cohort_takeaway(visible_counts, len(hidden), total),
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
