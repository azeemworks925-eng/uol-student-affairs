"""
The hidden component gallery (Polish v2): every shared component, in light and dark, for the owner
and later polish sessions. Not linked anywhere. A plain 404 unless DEBUG is True and the signed-in
user is staff, so it never exists in production.
"""

from datetime import timedelta

from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from . import tones


@require_GET
def component_gallery(request):
    user = request.user
    if not (settings.DEBUG and user.is_authenticated and user.is_staff):
        raise Http404("Not found.")
    now = timezone.now()
    journey = [
        {"label": "Received", "state": "done", "tone": "received"},
        {"label": "Under Review", "state": "current", "tone": "review"},
        {"label": "Resolved", "state": "upcoming", "tone": "resolved"},
    ]
    resolved = [
        {"label": "Received", "state": "done", "tone": "received"},
        {"label": "Under Review", "state": "done", "tone": "review"},
        {"label": "Resolved", "state": "current", "tone": "resolved"},
    ]
    rejected = [
        {"label": "Received", "state": "done", "tone": "received"},
        {"label": "Under Review", "state": "done", "tone": "review"},
        {"label": "Rejected", "state": "current", "tone": "rejected"},
    ]
    statuses = [
        ("complaint", value, label) for value, label in (("received", "Received"), ("under_review", "Under review"),
                                                         ("resolved", "Resolved"), ("rejected", "Rejected"))
    ] + [
        ("voice", value, label) for value, label in (("waiting", "Waiting"), ("reviewed", "Reviewed"), ("answered", "Answered"))
    ] + [
        ("issue", "support_open", "Open for support"), ("issue", "support_closed", "Support closed"),
    ] + [
        ("meeting", value, label) for value, label in (("requested", "Requested"), ("time_suggested", "Time suggested"),
                                                       ("confirmed", "Confirmed"), ("declined", "Declined"),
                                                       ("cancelled", "Cancelled"), ("past", "Past"))
    ] + [
        ("account", "active", "Active"), ("account", "inactive", "Inactive"),
        ("representation", "represented", "Represented"), ("representation", "awaiting", "Awaiting"),
    ]
    return render(request, "dev/gallery.html", {
        "now": now,
        "earlier": now - timedelta(days=2),
        "journey": journey,
        "journey_resolved": resolved,
        "journey_rejected": rejected,
        "statuses": statuses,
        "pastels": tones.PASTELS,
        "tones": tones.TONES,
        "voice_types": [("question", "Question"), ("idea", "Idea"), ("feedback", "Feedback")],
        "choices": [("", "All"), ("received", "Received"), ("under_review", "Under review"), ("resolved", "Resolved")],
        "themes": ("light", "dark"),
    })
