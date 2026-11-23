"""
Student complaint pages (Complaints Part 2): submit, My Submissions (DEC-031) and details.

Views stay thin:
- access: `student_required` (signed-in, active student; unregistered students are sent
  to registration by accounts.middleware) and, for one complaint, `get_visible_complaint`,
  which returns 404 for anything that is not the student's own;
- changes: only through complaints.services, which re-check ownership and the rules;
- the student and the cohort always come from the signed-in account, never from the form.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.permissions import student_required

from . import services
from .forms import CancellationRequestForm, ComplaintSubmissionForm, FurtherInformationForm, StillNotResolvedForm
from .models import Complaint, ComplaintCategory
from .ordering import DEFAULT_SORT, STUDENT_SORTS, clean_sort, sort_complaints
from .permissions import get_visible_complaint, visible_complaints
from .presentation import has_cancellation_request, status_journey, status_stats, status_tone, student_timeline

PAGE_SIZE = 10
LIST_PARAMS = ("q", "status", "category", "sort", "page")
Status = Complaint.Status
OPEN_STATUSES = (Status.RECEIVED, Status.UNDER_REVIEW)


def _apply_service_errors(form, error):
    """Show a service ValidationError on the form: on its field if the form has one."""
    if hasattr(error, "error_dict"):
        for field, field_errors in error.error_dict.items():
            form.add_error(field if field in form.fields else None, field_errors)
    else:
        form.add_error(None, error)


def _field_errors(form, error):
    """Whether a service error belongs to one of the form's fields."""
    return hasattr(error, "error_dict") and any(field in form.fields for field in error.error_dict)


def _similar_complaints(student, title):
    """For the non-blocking duplicate warning (DEC-225): the student's own open complaints with
    a similar title, from services.possible_duplicates. Only reference and title."""
    return [
        {"reference": c.reference, "title": c.title, "url": reverse("student_complaint_detail", args=[c.reference])}
        for c in services.possible_duplicates(student, title)
    ]


@student_required
@require_GET
def complaint_similar(request):
    """The duplicate warning's data while the student types a title. It changes nothing."""
    title = request.GET.get("title", "")[:Complaint._meta.get_field("title").max_length]
    return JsonResponse({"matches": _similar_complaints(request.user, title)})


@student_required
@require_http_methods(["GET", "POST"])
def complaint_new(request):
    # Bind on every POST: an entirely empty POST is a falsey QueryDict, and must still be
    # validated so the required-field errors are shown.
    form = ComplaintSubmissionForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            complaint = services.submit_complaint(
                request.user,
                category=data["category"],
                subcategory=data["subcategory"],
                title=data["title"],
                description=data["description"],
            )
        except ValidationError as error:
            _apply_service_errors(form, error)
        else:
            messages.success(request, f"Your complaint was submitted. Its reference is {complaint.reference}.")
            return redirect("student_complaint_detail", reference=complaint.reference)
    return render(request, "complaints/student/new.html", {
        "form": form,
        # After a failed submit the warning is already there, even without JavaScript.
        "similar": _similar_complaints(request.user, request.POST.get("title", "")) if form.is_bound else [],
    })


@student_required
def complaint_list(request):
    status = request.GET.get("status", "")
    if status not in Status.values:
        status = ""
    sort = clean_sort(request.GET.get("sort"), STUDENT_SORTS)
    own = visible_complaints(request.user)
    query = " ".join(request.GET.get("q", "").split())[:100]
    categories = list(ComplaintCategory.objects.filter(pk__in=own.order_by().values("category_id")).order_by("position", "name"))
    category = request.GET.get("category", "")
    if category not in {str(c.pk) for c in categories}:
        category = ""
    complaints = own.filter(status=status) if status else own
    if category:
        complaints = complaints.filter(category_id=int(category))
    if query:
        complaints = complaints.filter(Q(reference__icontains=query) | Q(title__icontains=query))
    complaints = complaints.annotate(last_activity=Max("events__created_at"), event_count=Count("events")).order_by()
    # Filtered in the database, merge-sorted in Python (dsa.sorting), then paginated.
    page = Paginator(sort_complaints(list(complaints), sort), PAGE_SIZE).get_page(request.GET.get("page"))
    for complaint in page:
        complaint.tone = status_tone(complaint.status)
    total = own.count()
    open_count = own.filter(status__in=OPEN_STATUSES).count() if total else 0
    return render(request, "complaints/student/list.html", {
        "page": page,
        "status": status,
        "filters": [("", "All")] + list(Status.choices),
        "category": category,
        "category_choices": [("", "All categories")] + [(str(c.pk), c.name) for c in categories],
        "query": query,
        "has_filters": bool(status or category or query),
        "sort": sort,
        "sort_current": sort if sort != DEFAULT_SORT else "",
        "sorts": STUDENT_SORTS,
        "list_keys": LIST_PARAMS,
        "list_query": _student_list_state(request.GET),
        "search_hidden": [(k, request.GET[k]) for k in ("status", "category", "sort") if request.GET.get(k)],
        "stats": status_stats(own),
        "total": total,
        "open_count": open_count,
    })


def _student_list_state(params):
    """The list's search, filters, sort and page, carried to a complaint and back."""
    return urlencode([(key, params[key]) for key in LIST_PARAMS if params.get(key)])


def _render_detail(request, complaint, status=200, **forms):
    is_open = complaint.status in OPEN_STATUSES
    list_state = _student_list_state(request.GET)
    cancellation_requested = has_cancellation_request(complaint)
    context = {
        "complaint": complaint,
        "tone": status_tone(complaint.status),
        "journey": status_journey(complaint),
        "timeline": student_timeline(complaint),  # students keep oldest first (P3-7)
        "last_activity": complaint.events.aggregate(latest=Max("created_at"))["latest"],
        "back_url": reverse("student_complaints") + (f"?{list_state}" if list_state else ""),
        "information_form": forms.get("information_form") or FurtherInformationForm(),
        "still_form": forms.get("still_form") or StillNotResolvedForm(),
        "cancel_form": forms.get("cancel_form") or CancellationRequestForm(),
        "can_mark_still_not_resolved": complaint.status == Status.RESOLVED,
        # Shown for open complaints until a request is recorded. What happens to a request
        # is OPEN (O28); this page only records it.
        "can_request_cancellation": is_open and not cancellation_requested,
        "cancellation_requested": cancellation_requested,
        "open_panel": forms.get("open_panel", ""),
    }
    return render(request, "complaints/student/detail.html", context, status=status)


@student_required
def complaint_detail(request, reference):
    return _render_detail(request, get_visible_complaint(request.user, reference))


def _student_action(request, reference, form_class, form_key, action, success_message):
    complaint = get_visible_complaint(request.user, reference)
    form = form_class(request.POST)
    if form.is_valid():
        try:
            action(request.user, complaint, *form.cleaned_data.values())
        except ValidationError as error:
            if not _field_errors(form, error):
                # The complaint's state does not allow this (for example, "Still not resolved"
                # on a complaint that is not Resolved): say so on the page, change nothing.
                messages.error(request, " ".join(error.messages))
                return redirect("student_complaint_detail", reference=complaint.reference)
            _apply_service_errors(form, error)
        else:
            messages.success(request, success_message)
            return redirect("student_complaint_detail", reference=complaint.reference)
    complaint.refresh_from_db()
    return _render_detail(request, complaint, status=400, **{form_key: form, "open_panel": form_key})


@student_required
@require_POST
def complaint_add_information(request, reference):
    return _student_action(
        request, reference, FurtherInformationForm, "information_form",
        services.add_further_information, "Your information was added to the complaint.",
    )


@student_required
@require_POST
def complaint_still_not_resolved(request, reference):
    return _student_action(
        request, reference, StillNotResolvedForm, "still_form",
        services.mark_still_not_resolved, "Thank you. Your complaint is back Under Review.",
    )


@student_required
@require_POST
def complaint_request_cancellation(request, reference):
    return _student_action(
        request, reference, CancellationRequestForm, "cancel_form",
        services.request_cancellation, "Your cancellation request was recorded.",
    )
