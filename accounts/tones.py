"""
The one status colour map for the whole portal (Polish v2, docs/POLISH_V2.md).

Every status, state, category and Student Voice type is mapped to a *tone* here, and only here.
Templates ask for a tone with the `tone` filter (`{{ complaint.status|tone }}`) and render
`sa-tone--<tone>`; the colours themselves live in static/css/app.css as tokens. No template or
view decides a colour on its own.

Tones are the five semantic tones (received, review, resolved, rejected, neutral). Categories and
Voice types use a fixed pastel family (mint, sky, amber, rose, lavender, peach, sand).
"""

from complaints.models import ComplaintStatus
from issues.models import CollectiveIssue
from meetings.models import Meeting
from voice.models import Submission

RECEIVED, REVIEW, RESOLVED, REJECTED, NEUTRAL = "received", "review", "resolved", "rejected", "neutral"
TONES = (RECEIVED, REVIEW, RESOLVED, REJECTED, NEUTRAL)
PASTELS = ("mint", "sky", "amber", "rose", "lavender", "peach", "sand")

# Each domain's states. The keys are the stored values (or derived state names).
COMPLAINT = {
    ComplaintStatus.RECEIVED: RECEIVED,
    ComplaintStatus.UNDER_REVIEW: REVIEW,
    ComplaintStatus.RESOLVED: RESOLVED,
    ComplaintStatus.REJECTED: REJECTED,
}
VOICE = {
    Submission.Status.WAITING: RECEIVED,
    Submission.Status.REVIEWED: REVIEW,
    Submission.Status.ANSWERED: RESOLVED,
}
ISSUE = {
    CollectiveIssue.Status.RECEIVED: RECEIVED,
    CollectiveIssue.Status.UNDER_REVIEW: REVIEW,
    CollectiveIssue.Status.RESOLVED: RESOLVED,
    # Derived support states (CollectiveIssue.support_is_open).
    "support_open": RESOLVED,
    "support_closed": NEUTRAL,
}
MEETING = {
    Meeting.Status.REQUESTED: RECEIVED,
    Meeting.Status.TIME_SUGGESTED: REVIEW,
    Meeting.Status.CONFIRMED: RESOLVED,
    Meeting.Status.DECLINED: REJECTED,
    Meeting.Status.CANCELLED: REJECTED,
    "past": NEUTRAL,  # a meeting whose time has passed
}
ACCOUNT = {"active": RESOLVED, "inactive": NEUTRAL}
REPRESENTATION = {"represented": RESOLVED, "awaiting": REVIEW}

DOMAINS = {
    "complaint": COMPLAINT,
    "voice": VOICE,
    "issue": ISSUE,
    "meeting": MEETING,
    "account": ACCOUNT,
    "representation": REPRESENTATION,
}

# Plain lookup by value. The same stored value always means the same tone in every domain
# (for example "received" and "under_review" in complaints and section issues), which the tests
# check, so templates can pass a bare status.
_BY_VALUE = {}
for _domain in DOMAINS.values():
    for _key, _tone in _domain.items():
        _BY_VALUE[str(_key)] = _tone

# Student Voice types: fixed pastels.
VOICE_TYPE = {
    Submission.Type.QUESTION: "sky",
    Submission.Type.IDEA: "amber",
    Submission.Type.FEEDBACK: "lavender",
}

# Tone -> the pastel family it is drawn in (mirrors the --tone-* tokens in app.css).
TONE_PASTEL = {RECEIVED: "sky", REVIEW: "amber", RESOLVED: "mint", REJECTED: "rose", NEUTRAL: "sand"}

# Complaint categories cycle through these (a stable order, by position then id).
CATEGORY_PASTELS = ("mint", "sky", "lavender", "peach", "amber", "rose", "sand")

# Notification event types (notifications.registry) -> the tone of their icon chip, and the icon
# for each module.
NOTIFICATION_TONES = {
    "complaint.status_changed": REVIEW,
    "complaint.response": RECEIVED,
    "voice.answered": RESOLVED,
    "voice.replied": RECEIVED,
    "meeting.confirmed": RESOLVED,
    "meeting.time_suggested": REVIEW,
    "meeting.declined": REJECTED,
    "meeting.cancelled": REJECTED,
    "issue.published": RECEIVED,
    "issue.response": RECEIVED,
    "issue.resolved": RESOLVED,
}
NOTIFICATION_ICONS = {"complaint": "file", "voice": "voice", "meeting": "calendar", "issue": "hand"}


def tone(value, domain=None):
    """The tone for a status or state. Unknown values are neutral."""
    if value is None:
        return NEUTRAL
    key = str(getattr(value, "value", value))
    if domain is not None:
        return DOMAINS.get(domain, {}).get(key, NEUTRAL)
    return _BY_VALUE.get(key, NEUTRAL)


def voice_type_pastel(value):
    return VOICE_TYPE.get(str(getattr(value, "value", value)), "sand")


def category_pastel(category):
    """A category's fixed pastel: chosen from its id so it never changes when others move."""
    pk = getattr(category, "pk", category)
    try:
        return CATEGORY_PASTELS[int(pk) % len(CATEGORY_PASTELS)]
    except (TypeError, ValueError):
        return "sand"


def notification_tone(event_type):
    return NOTIFICATION_TONES.get(str(event_type or ""), NEUTRAL)


def notification_icon(event_type):
    return NOTIFICATION_ICONS.get(str(event_type or "").split(".", 1)[0], "bell")
