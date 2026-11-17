"""
Staff complaints workspace, shared by the Batch Advisor (Complaints Part 3) and the Super Admin
(Part 4 Stage 1). Specifications: docs/technical/COMPLAINTS_PART3_SPEC.md and
COMPLAINTS_PART4_SPEC.md section 3.

One view and one template serve the list and the selected case for each role; the URL decides
whether a case is selected and CSS decides the layout. A `Workspace` describes what differs by
role. Access is the same for both:
- the role decorator is on every view (in advisor_views / admin_views);
- lists start from `visible_complaints(user)` and filters only narrow it (Batch Advisors: exact
  batch + semester + section assignments, DEC-205; Super Admins: every complaint);
- a case is always loaded with `get_visible_complaint`, on GET and POST;
- changes go only through complaints.services.

Not here, by decision: automatic owner assignment (DEC-310), cancellation handling (DEC-311),
a "Waiting for you" queue (DEC-312), the student's other complaints (DEC-305) and the
student's current cohort (P3-5).
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Exists, Max, OuterRef, Q
from django.shortcuts import redirect, render
from django.urls import reverse

from accounts.models import AdvisorAssignment, StudentProfile, User
from academics.models import AcademicTerm, Batch, Section, Semester

from . import services
from .forms import AdvisorResponseForm, ComplaintListFilterForm, ResponsibleOwnerForm, StatusUpdateForm
from .models import Complaint, ComplaintCategory, ComplaintEvent
from .permissions import get_visible_complaint, visible_complaints
from .presentation import staff_timeline, status_journey, status_tone

PAGE_SIZE = 20
LIST_PARAMS = ("q", "cohort", "status", "category", "owner", "sort", "page")
FILTER_PARAMS = ("q", "cohort", "status", "category", "owner")
# The Super Admin list also filters by academic term (Part 4 Stage 4a). The Batch Advisor list
# keeps the tuples above, so a `term` parameter is neither applied nor carried there.
SUPER_ADMIN_LIST_PARAMS = ("q", "cohort", "status", "category", "owner", "term", "sort", "page")
SUPER_ADMIN_FILTER_PARAMS = (*FILTER_PARAMS, "term")
Status = Complaint.Status
Kind = ComplaintEvent.Kind
OPEN_STATUSES = (Status.RECEIVED, Status.UNDER_REVIEW)


@dataclass(frozen=True)
class Workspace:
    """What differs between the Batch Advisor and Super Admin workspaces."""

    url_prefix: str  # URL names: <prefix>s, <prefix>_detail, <prefix>_respond, <prefix>_status, <prefix>_owner
    department_wide: bool  # Super Admin: every cohort, owner filter and panel, owner history

    @property
    def list_params(self):
        return SUPER_ADMIN_LIST_PARAMS if self.department_wide else LIST_PARAMS

    @property
    def filter_params(self):
        return SUPER_ADMIN_FILTER_PARAMS if self.department_wide else FILTER_PARAMS

    def url(self, name, *args):
        return reverse(f"{self.url_prefix}{name}", args=args)

    @property
    def url_names(self):
        names = {"list": f"{self.url_prefix}s", "detail": f"{self.url_prefix}_detail",
                 "respond": f"{self.url_prefix}_respond", "status": f"{self.url_prefix}_status"}
        if self.department_wide:
            names["owner"] = f"{self.url_prefix}_owner"
        return names


ADVISOR = Workspace(url_prefix="advisor_complaint", department_wide=False)
SUPER_ADMIN = Workspace(url_prefix="super_admin_complaint", department_wide=True)


def cohort_value(batch_id, semester_id, section_id):
    """The cohort filter value: the exact batch + semester + section (DEC-205)."""
    return f"{batch_id}.{semester_id}.{section_id}"


def _cohort_choices(triples):
    """(value, label) choices for distinct (batch, semester, section) triples, in academic order."""
    triples = set(triples)
    batches = Batch.objects.in_bulk({t[0] for t in triples})
    semesters = Semester.objects.in_bulk({t[1] for t in triples})
    sections = Section.objects.in_bulk({t[2] for t in triples})
    rows = [(batches[b], semesters[s], sections[c]) for b, s, c in triples]
    rows.sort(key=lambda r: (r[0].name, r[1].number, r[2].name))
    return [(cohort_value(b.pk, s.pk, c.pk), f"{b} · {s} · {c}") for b, s, c in rows]


def advisor_cohorts(user):
    """The advisor's own assignments as (value, label) filter choices, in academic order."""
    return _cohort_choices(
        AdvisorAssignment.objects.filter(advisor=user).values_list("batch_id", "semester_id", "section_id")
    )


def department_cohorts():
    """Every known cohort: from advisor assignments, student registrations and complaints, so a
    real cohort can be chosen even when it has no complaints yet (Part 4 section 3.1)."""
    fields = ("batch_id", "semester_id", "section_id")
    return _cohort_choices([
        *AdvisorAssignment.objects.values_list(*fields),
        *StudentProfile.objects.values_list(*fields),
        *Complaint.objects.values_list(*fields),
    ])


def list_state(params, *, without=(), keys=LIST_PARAMS):
    """The list's query string (search, filters, sort, page) to carry between list and case.
    `keys` is the workspace's own parameter list (Workspace.list_params)."""
    return urlencode([(key, params[key]) for key in keys if key not in without and params.get(key)])


def _headline(visible, workspace):
    counts = dict(visible.values_list("status").annotate(n=Count("id")).order_by())
    received, review = counts.get(Status.RECEIVED, 0), counts.get(Status.UNDER_REVIEW, 0)
    scope = "the department" if workspace.department_wide else "your cohorts"
    if not sum(counts.values()):
        return "No complaints have been submitted yet." if workspace.department_wide else "There are no complaints in your cohorts."
    if not received + review:
        return f"There are no open complaints in {scope}."
    open_total = received + review
    noun = "complaint" if open_total == 1 else "complaints"
    parts = [f"{n} {label}" for n, label in ((received, "received"), (review, "under review")) if n]
    subject = "The department has" if workspace.department_wide else "Your cohorts have"
    return f"{subject} {open_total} open {noun}: {' and '.join(parts)}."


def _filtered(visible, filters, workspace, term=None):
    complaints = visible
    if term is not None:
        # Submission date within the term's reporting window (academics.models.term_window).
        start, end = term.window()
        complaints = complaints.filter(created_at__gte=start, created_at__lt=end)
    q = filters.value("q")
    if q:
        search = (
            Q(reference__icontains=q)
            | Q(student__full_name__icontains=q)
            | Q(student__student_profile__sap_id__startswith=q)  # P3-3
        )
        if workspace.department_wide:
            search |= Q(title__icontains=q)  # Part 4 section 3.1
        complaints = complaints.filter(search)
    cohort = filters.value("cohort")
    if cohort:  # Validated against the offered choices.
        batch_id, semester_id, section_id = (int(part) for part in cohort.split("."))
        complaints = complaints.filter(batch_id=batch_id, semester_id=semester_id, section_id=section_id)
    status = filters.value("status")
    if status == ComplaintListFilterForm.OPEN:
        complaints = complaints.filter(status__in=OPEN_STATUSES)
    elif status:
        complaints = complaints.filter(status=status)
    category = filters.value("category")
    if category:
        complaints = complaints.filter(category_id=int(category))
    owner = filters.value("owner") if workspace.department_wide else ""
    if owner == ComplaintListFilterForm.UNASSIGNED:
        complaints = complaints.filter(responsible__isnull=True)
    elif owner:
        complaints = complaints.filter(responsible_id=int(owner))
    complaints = complaints.annotate(
        last_activity=Max("events__created_at"),
        # Factual labels only (P3-2): recorded events, never "needs a response" (DEC-312).
        cancellation_requested=Exists(ComplaintEvent.objects.filter(complaint=OuterRef("pk"), kind=Kind.CANCELLATION_REQUESTED)),
        reopened=Exists(ComplaintEvent.objects.filter(complaint=OuterRef("pk"), kind=Kind.STILL_NOT_RESOLVED)),
    )
    order = ("-created_at", "-id") if filters.value("sort") == "newest" else ("-last_activity", "-id")
    return complaints.order_by(*order)


def _owner_context(user, complaint, forms):
    owner = complaint.responsible
    return {
        "owner": owner,
        "owner_label": f"{owner.get_full_name()} ({owner.get_role_display()})" if owner else "",
        # Factual: the owner no longer meets DEC-310 (deactivated or reassigned off the cohort).
        "owner_no_longer_eligible": bool(owner) and not services.is_eligible_owner(owner, complaint),
        "owner_form": forms.get("owner_form") or ResponsibleOwnerForm(
            complaint=complaint, actor=user, initial={"owner": str(owner.pk)} if owner else None,
        ),
    }


def _case_context(user, complaint, forms, workspace):
    assignments = (
        AdvisorAssignment.objects.filter(
            batch_id=complaint.batch_id, semester_id=complaint.semester_id, section_id=complaint.section_id,
            advisor__is_active=True,
        )
        .select_related("advisor")
        .order_by("advisor__full_name", "advisor__email")
    )
    profile = getattr(complaint.student, "student_profile", None)
    status_form = forms.get("status_form") or StatusUpdateForm(complaint=complaint)
    context = {
        "complaint": complaint,
        "tone": status_tone(complaint.status),
        "journey": status_journey(complaint),
        "timeline": staff_timeline(complaint, include_owner_changes=workspace.department_wide),
        "response_form": forms.get("response_form") or AdvisorResponseForm(),
        "status_form": status_form,
        "can_update_status": bool(status_form.fields["new_status"].choices),
        "error_panel": forms.get("error_panel", ""),
        # P3-1 and P3-5: name and SAP ID, and only the cohort recorded at submission.
        "student_name": complaint.student.get_full_name(),
        "sap_id": profile.sap_id if profile else "",
        "cohort_advisors": [
            {"name": a.advisor.get_full_name(), "is_you": a.advisor_id == user.pk} for a in assignments
        ],
    }
    if workspace.department_wide:
        context.update(_owner_context(user, complaint, forms))
    return context


def render_workspace(request, workspace, reference=None, status=200, **forms):
    user = request.user
    visible = visible_complaints(user)
    cohorts = department_cohorts() if workspace.department_wide else advisor_cohorts(user)
    categories = ComplaintCategory.objects.filter(pk__in=visible.values("category_id")).order_by("position", "name")
    owners = (
        User.objects.filter(pk__in=visible.exclude(responsible=None).values("responsible_id")).order_by("full_name", "email")
        if workspace.department_wide else None
    )
    terms = list(AcademicTerm.objects.all()) if workspace.department_wide else None
    filters = ComplaintListFilterForm(
        request.GET, cohorts=cohorts, categories=categories, owners=owners, terms=terms,
        include_open=not workspace.department_wide,
        all_cohorts_label="All cohorts" if workspace.department_wide else "All assigned cohorts",
    )
    # Only an existing term chosen from the form's choices filters; anything else is ignored.
    selected_term = next((t for t in terms if str(t.pk) == filters.value("term")), None) if terms else None
    page = Paginator(_filtered(visible, filters, workspace, selected_term), PAGE_SIZE).get_page(request.GET.get("page"))
    for item in page:
        item.tone = status_tone(item.status)

    # An empty selected cohort is told apart from filters that match nothing (Part 4 3.1).
    selected_cohort, empty_cohort_label = filters.value("cohort"), ""
    if selected_cohort and not page.object_list:
        batch_id, semester_id, section_id = (int(part) for part in selected_cohort.split("."))
        if not visible.filter(batch_id=batch_id, semester_id=semester_id, section_id=section_id).exists():
            empty_cohort_label = dict(cohorts)[selected_cohort]
    keys = workspace.list_params
    state = list_state(request.GET, keys=keys)
    context = {
        "workspace": workspace,
        "urls": workspace.url_names,
        "filters": filters,
        "show_cohort_filter": len(cohorts) > 1 or (workspace.department_wide and bool(cohorts)),
        "has_filters": any(filters.value(name) for name in workspace.filter_params),
        "selected_term": selected_term,
        "term_clear_url": workspace.url("s") + (
            f"?{without_term}" if (without_term := list_state(request.GET, without=("term", "page"), keys=keys)) else ""
        ),
        "page": page,
        "headline": _headline(visible, workspace),
        "has_assignments": bool(cohorts) or workspace.department_wide,
        "cohort_labels": [] if workspace.department_wide else [label for _, label in cohorts],
        "empty_cohort_label": empty_cohort_label,
        "list_state": state,
        "list_state_without_page": list_state(request.GET, without=("page",), keys=keys),
        "list_url": workspace.url("s") + (f"?{state}" if state else ""),
        "selected_reference": reference,
    }
    if reference:
        context.update(_case_context(user, get_visible_complaint(user, reference), forms, workspace))
    return render(request, "complaints/workspace/workspace.html", context, status=status)


def _case_url(workspace, complaint, request):
    state = list_state(request.GET, keys=workspace.list_params)
    return workspace.url("_detail", complaint.reference) + (f"?{state}" if state else "")


def staff_action(request, workspace, reference, form, panel, action, success_message):
    """Run one service action for the selected case: Post/Redirect/Get on success, the case
    with the form's errors (HTTP 400) on invalid input, and a message when the complaint's
    current state no longer allows the action."""
    complaint = get_visible_complaint(request.user, reference)
    if form.is_valid():
        try:
            outcome = action(complaint, form.cleaned_data)
        except ValidationError as error:
            if not (hasattr(error, "error_dict") and any(field in form.fields for field in error.error_dict)):
                # For example, a colleague changed the status first: explain, change nothing,
                # and show the current state.
                messages.error(request, " ".join(error.messages))
                return redirect(_case_url(workspace, complaint, request))
            for field, field_errors in error.error_dict.items():
                form.add_error(field if field in form.fields else None, field_errors)
        else:
            messages.success(request, outcome if isinstance(outcome, str) else success_message)
            return redirect(_case_url(workspace, complaint, request))
    return render_workspace(request, workspace, reference, status=400, **{f"{panel}_form": form, "error_panel": panel})


def respond(request, workspace, reference):
    return staff_action(
        request, workspace, reference, AdvisorResponseForm(request.POST), "response",
        lambda complaint, data: services.respond(request.user, complaint, data["message"]),
        "Your response was sent. The status did not change.",
    )


def update_status(request, workspace, reference):
    complaint = get_visible_complaint(request.user, reference)
    return staff_action(
        request, workspace, reference,
        StatusUpdateForm(request.POST, complaint=complaint, seen_status=request.POST.get("expected_status")),
        "status",
        lambda complaint, data: services.change_status(
            request.user, complaint, data["new_status"], data["note"], expected_status=data["expected_status"],
        ),
        "The status was updated.",
    )


def assign_owner(request, workspace, reference):
    complaint = get_visible_complaint(request.user, reference)

    def assign(complaint, data):
        owner = data["owner"]
        if complaint.responsible_id == owner.pk:
            # services.assign_responsible treats this as a no-op (no event); say so plainly.
            return f"No change: {owner.get_full_name()} is already the responsible owner."
        services.assign_responsible(request.user, complaint, owner)
        if owner.pk == request.user.pk:
            return "You are now the responsible owner of this complaint."
        return f"{owner.get_full_name()} is now the responsible owner of this complaint."

    return staff_action(
        request, workspace, reference,
        ResponsibleOwnerForm(request.POST, complaint=complaint, actor=request.user),
        "owner", assign, "",
    )
