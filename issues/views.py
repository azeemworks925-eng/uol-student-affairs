"""
Section issue pages. Views stay thin:
- the role decorator is on every view;
- records are loaded through issues.permissions, so anything not visible is a 404;
- changes go only through issues.services.
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.permissions import student_required

from . import services
from .permissions import get_visible_issue, is_cohort_student, is_current_representative_of
from .presentation import add_display, private_responses, status_journey, supported_ids


def _detail_context(user, issue, *, show_private):
    add_display([issue])
    context = {"issue": issue, "show_private": show_private}
    if show_private:
        context.update({"journey": status_journey(issue), "responses": private_responses(issue)})
    return context


@student_required
def student_issue_detail(request, reference):
    issue = get_visible_issue(request.user, reference)
    is_rep = is_current_representative_of(request.user, issue)
    context = _detail_context(request.user, issue, show_private=is_rep)
    context.update({
        "is_rep": is_rep,
        "can_support": issue.support_is_open and is_cohort_student(request.user, issue),
        "has_supported": issue.pk in supported_ids(request.user, [issue]),
        "back_url": reverse("student_home"),
        "back_label": "Back to Home",
    })
    return render(request, "issues/detail.html", context)


@student_required
@require_POST
def student_issue_support(request, reference):
    issue = get_visible_issue(request.user, reference)
    try:
        recorded = services.support_issue(request.user, issue)
    except PermissionDenied:
        raise Http404("No issue found.") from None
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        if recorded:
            messages.success(request, "Your support has been recorded.")
        else:
            messages.info(request, "You already support this issue.")
    if request.POST.get("from") == "home":
        return redirect("student_home")
    return redirect("student_issue_detail", reference=issue.reference)
