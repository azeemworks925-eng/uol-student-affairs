"""
Batch Advisor complaints workspace (Complaints Part 3; docs/technical/COMPLAINTS_PART3_SPEC.md).

Thin views over complaints.workspace (shared with the Super Admin workspace). Every view requires
an active Batch Advisor; the workspace scopes everything to their exact assigned cohorts.
"""

from django.views.decorators.http import require_POST

from accounts.permissions import batch_advisor_required

from . import workspace
from .workspace import ADVISOR, PAGE_SIZE, advisor_cohorts, cohort_value, list_state  # noqa: F401  (public helpers)


@batch_advisor_required
def workspace_view(request, reference=None):
    return workspace.render_workspace(request, ADVISOR, reference)


@batch_advisor_required
def go_to_reference(request):
    return workspace.go_to_reference(request, ADVISOR)


@batch_advisor_required
def next_complaint(request):
    return workspace.next_complaint(request, ADVISOR)


@batch_advisor_required
@require_POST
def respond(request, reference):
    return workspace.respond(request, ADVISOR, reference)


@batch_advisor_required
@require_POST
def update_status(request, reference):
    return workspace.update_status(request, ADVISOR, reference)
