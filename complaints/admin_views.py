"""
Super Admin complaints workspace (Complaints Part 4 Stage 1; COMPLAINTS_PART4_SPEC.md section 3).

Thin views over complaints.workspace. Every view requires an active Super Admin
(`super_admin_required`); the role comes from the signed-in account, never from the request.
Department-wide visibility comes from `visible_complaints`; changes go through
complaints.services, including manual owner assignment (DEC-310).
"""

from django.views.decorators.http import require_POST

from accounts.permissions import super_admin_required

from . import workspace
from .workspace import SUPER_ADMIN


@super_admin_required
def workspace_view(request, reference=None):
    return workspace.render_workspace(request, SUPER_ADMIN, reference)


@super_admin_required
@require_POST
def respond(request, reference):
    return workspace.respond(request, SUPER_ADMIN, reference)


@super_admin_required
@require_POST
def update_status(request, reference):
    return workspace.update_status(request, SUPER_ADMIN, reference)


@super_admin_required
@require_POST
def assign_owner(request, reference):
    return workspace.assign_owner(request, SUPER_ADMIN, reference)
