"""
The signed-in user's notifications (Complaints Part 4 Stage 3; spec section 5.1).

- Every view requires a signed-in user (inactive users are signed out by the auth backend) and
  works only on that user's own notifications; another user's id is a plain 404.
- Opening is POST + CSRF: it marks the notification read, then redirects to the destination built
  by services.destination_url from the registry (never from the request). The destination view
  applies its own permission checks: a notification grants no access.
- Viewing the list does not mark anything read.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from . import services

PAGE_SIZE = 20


@login_required
@require_GET
def notification_list(request):
    page = Paginator(services.for_user(request.user), PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "notifications/list.html", {
        "page": page,
        "unread": services.unread_count(request.user),
    })


@login_required
@require_POST
def notification_open(request, pk):
    notification = services.mark_read(request.user, pk)
    if notification is None:
        raise Http404("No notification found.")
    url = services.destination_url(notification)
    if url is None:
        messages.error(request, "That notification’s page is no longer available.")
        return redirect("notifications")
    response = HttpResponseRedirect(url)
    response.status_code = 303  # POST, then GET the destination
    return response


def _wants_json(request):
    return "application/json" in request.headers.get("Accept", "")


@login_required
@require_POST
def notification_mark_all_read(request):
    """Mark all of the user's own notifications read. A fetch from the bell panel gets JSON; a
    plain form post goes back to `next` (same site only) or the notifications page."""
    count = services.mark_all_read(request.user)
    if _wants_json(request):
        return JsonResponse({"marked": count, "unread": 0})
    messages.success(request, "All caught up" if count else "Nothing unread")
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                  require_https=request.is_secure()):
        return redirect(target)
    return redirect("notifications")
