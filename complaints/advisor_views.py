"""
Batch Advisor complaints workspace (Complaints Part 3; docs/technical/COMPLAINTS_PART3_SPEC.md).

One view and one template serve the list and the selected case; the URL decides whether a
case is selected and CSS decides the layout. Access:
- `batch_advisor_required` on every view;
- lists start from `visible_complaints(user)` (exact assigned cohorts, DEC-205) and filters
  only narrow it; a case is always loaded with `get_visible_complaint`, so an out-of-cohort
  reference returns the same 404 as an unknown one, on GET and POST;
- changes go only through complaints.services.

Not here, by decision: a responsible owner (O27), cancellation handling (O28), a
"Waiting for you" queue or response-required grouping (O33), the student's other
complaints (DEC-305) and the student's current cohort (P3-5).
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Exists, Max, OuterRef, Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import AdvisorAssignment
from accounts.permissions import batch_advisor_required

from . import services
from .forms import AdvisorResponseForm, ComplaintListFilterForm, StatusUpdateForm
from .models import Complaint, ComplaintCategory, ComplaintEvent
from .permissions import get_visible_complaint, visible_complaints
from .presentation import staff_timeline, status_journey, status_tone

PAGE_SIZE = 20
LIST_PARAMS = ("q", "cohort", "status", "category", "sort", "page")
Status = Complaint.Status
Kind = ComplaintEvent.Kind
OPEN_STATUSES = (Status.RECEIVED, Status.UNDER_REVIEW)


def cohort_value(batch_id, semester_id, section_id):
    """The cohort filter value: the exact batch + semester + section (DEC-205)."""
    return f"{batch_id}.{semester_id}.{section_id}"


def advisor_cohorts(user):
    """The advisor's own assignments as (value, label) filter choices, in academic order."""
    assignments = (
        AdvisorAssignment.objects.filter(advisor=user)
        .select_related("batch", "semester", "section")
        .order_by("batch__name", "semester__number", "section__name")
    )
    return [
        (cohort_value(a.batch_id, a.semester_id, a.section_id), f"{a.batch} · {a.semester} · {a.section}")
        for a in assignments
    ]


def list_state(params, *, without=()):
    """The list's query string (search, filters, sort, page) to carry between list and case."""
    return urlencode([(key, params[key]) for key in LIST_PARAMS if key not in without and params.get(key)])


def _headline(visible):
    counts = dict(visible.values_list("status").annotate(n=Count("id")).order_by())
    received, review = counts.get(Status.RECEIVED, 0), counts.get(Status.UNDER_REVIEW, 0)
    if not sum(counts.values()):
        return "There are no complaints in your cohorts."
    if not received + review:
        return "There are no open complaints in your cohorts."
    open_total = received + review
    noun = "complaint" if open_total == 1 else "complaints"
    parts = [f"{n} {label}" for n, label in ((received, "received"), (review, "under review")) if n]
    return f"Your cohorts have {open_total} open {noun}: {' and '.join(parts)}."


def _filtered(visible, filters):
    complaints = visible
    q = filters.value("q")
    if q:
        complaints = complaints.filter(
            Q(reference__icontains=q)
            | Q(student__full_name__icontains=q)
            | Q(student__student_profile__sap_id__startswith=q)  # P3-3
        )
    cohort = filters.value("cohort")
    if cohort:  # Already validated against the advisor's own assignments.
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
    complaints = complaints.annotate(
        last_activity=Max("events__created_at"),
        # Factual labels only (P3-2): recorded events, never "needs a response" (O33).
        cancellation_requested=Exists(ComplaintEvent.objects.filter(complaint=OuterRef("pk"), kind=Kind.CANCELLATION_REQUESTED)),
        reopened=Exists(ComplaintEvent.objects.filter(complaint=OuterRef("pk"), kind=Kind.STILL_NOT_RESOLVED)),
    )
    order = ("-created_at", "-id") if filters.value("sort") == "newest" else ("-last_activity", "-id")
    return complaints.order_by(*order)


def _case_context(user, complaint, forms):
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
    return {
        "complaint": complaint,
        "tone": status_tone(complaint.status),
        "journey": status_journey(complaint),
        "timeline": staff_timeline(complaint),
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


def _render_workspace(request, reference=None, status=200, **forms):
    user = request.user
    visible = visible_complaints(user)
    cohorts = advisor_cohorts(user)
    categories = ComplaintCategory.objects.filter(pk__in=visible.values("category_id")).order_by("position", "name")
    filters = ComplaintListFilterForm(request.GET, cohorts=cohorts, categories=categories)
    page = Paginator(_filtered(visible, filters), PAGE_SIZE).get_page(request.GET.get("page"))
    for item in page:
        item.tone = status_tone(item.status)

    state = list_state(request.GET)
    context = {
        "filters": filters,
        "show_cohort_filter": len(cohorts) > 1,
        "has_filters": any(filters.value(name) for name in ("q", "cohort", "status", "category")),
        "page": page,
        "headline": _headline(visible),
        "has_assignments": bool(cohorts),
        "cohort_labels": [label for _, label in cohorts],
        "list_state": state,
        "list_state_without_page": list_state(request.GET, without=("page",)),
        "list_url": reverse("advisor_complaints") + (f"?{state}" if state else ""),
        "selected_reference": reference,
    }
    if reference:
        context.update(_case_context(user, get_visible_complaint(user, reference), forms))
    return render(request, "complaints/advisor/workspace.html", context, status=status)


@batch_advisor_required
def workspace(request, reference=None):
    return _render_workspace(request, reference)


def _case_url(complaint, request):
    state = list_state(request.GET)
    return reverse("advisor_complaint_detail", args=[complaint.reference]) + (f"?{state}" if state else "")


def _advisor_action(request, reference, form, panel, action, success_message):
    complaint = get_visible_complaint(request.user, reference)
    if form.is_valid():
        try:
            action(complaint, form.cleaned_data)
        except ValidationError as error:
            if not (hasattr(error, "error_dict") and any(field in form.fields for field in error.error_dict)):
                # The complaint's state no longer allows this (for example, a colleague changed
                # it first): explain, change nothing, and show the current state.
                messages.error(request, " ".join(error.messages))
                return redirect(_case_url(complaint, request))
            for field, field_errors in error.error_dict.items():
                form.add_error(field if field in form.fields else None, field_errors)
        else:
            messages.success(request, success_message)
            return redirect(_case_url(complaint, request))
    return _render_workspace(request, reference, status=400, **{f"{panel}_form": form, "error_panel": panel})


@batch_advisor_required
@require_POST
def respond(request, reference):
    return _advisor_action(
        request, reference, AdvisorResponseForm(request.POST), "response",
        lambda complaint, data: services.respond(request.user, complaint, data["message"]),
        "Your response was sent. The status did not change.",
    )


@batch_advisor_required
@require_POST
def update_status(request, reference):
    complaint = get_visible_complaint(request.user, reference)
    return _advisor_action(
        request, reference,
        StatusUpdateForm(request.POST, complaint=complaint, seen_status=request.POST.get("expected_status")),
        "status",
        lambda complaint, data: services.change_status(
            request.user, complaint, data["new_status"], data["note"], expected_status=data["expected_status"],
        ),
        "The status was updated.",
    )
