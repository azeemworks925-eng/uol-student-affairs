"""
How complaints read to the student who submitted them (Complaints Part 2).

Only recorded events are shown, in order, with plain-language labels. Staff appear by role,
never by name or account. Changes of responsible owner are internal to staff while O27 is
open, so they are not part of the student's timeline.
"""

from dataclasses import dataclass

from .models import Complaint, ComplaintEvent

Status = Complaint.Status
Kind = ComplaintEvent.Kind

# The existing status pill tones in static/css/app.css (DEC-301).
STATUS_TONES = {
    Status.RECEIVED: "received",
    Status.UNDER_REVIEW: "review",
    Status.RESOLVED: "resolved",
    Status.REJECTED: "rejected",
}

STUDENT_HIDDEN_KINDS = {Kind.RESPONSIBLE_CHANGED}

MESSAGE_LABELS = {
    Status.RESOLVED: "Resolution note",
    Status.REJECTED: "Reason for rejection",
}


def status_tone(status):
    return STATUS_TONES.get(status, "received")


@dataclass(frozen=True)
class TimelineEntry:
    title: str
    when: object
    by: str = ""
    message: str = ""
    message_label: str = ""
    status: str = ""  # the status the complaint moved to, if any
    note: str = ""
    by_student: bool = False

    @property
    def status_label(self):
        return Status(self.status).label if self.status else ""

    @property
    def tone(self):
        return status_tone(self.status) if self.status else ""


def _staff_role(actor):
    return actor.get_role_display()


def student_timeline(complaint):
    """The complaint's history as the student sees it, oldest first."""
    entries = []
    events = complaint.events.select_related("actor").exclude(kind__in=STUDENT_HIDDEN_KINDS).order_by("created_at", "id")
    for event in events:
        kind = event.kind
        if kind == Kind.SUBMITTED:
            entries.append(TimelineEntry("You submitted this complaint", event.created_at, by_student=True, status=Status.RECEIVED))
        elif kind == Kind.STATUS_CHANGED:
            new = Status(event.to_status)
            entries.append(TimelineEntry(
                f"Status changed to {new.label}", event.created_at, by=_staff_role(event.actor),
                message=event.message, message_label=MESSAGE_LABELS.get(new, "Note"), status=new,
            ))
        elif kind == Kind.STILL_NOT_RESOLVED:
            entries.append(TimelineEntry(
                "You said this is still not resolved", event.created_at, message=event.message,
                message_label="Your note", status=Status.UNDER_REVIEW, by_student=True,
                note="The complaint returned to Under Review.",
            ))
        elif kind == Kind.RESPONSE:
            entries.append(TimelineEntry(
                f"Response from {_staff_role(event.actor)}", event.created_at, message=event.message,
            ))
        elif kind == Kind.FURTHER_INFORMATION:
            entries.append(TimelineEntry(
                "You added further information", event.created_at, message=event.message, by_student=True,
            ))
        elif kind == Kind.CANCELLATION_REQUESTED:
            entries.append(TimelineEntry(
                "You asked to cancel this complaint", event.created_at, message=event.message,
                message_label="Your reason", by_student=True,
                note="Your request was recorded. It does not cancel or change the complaint by itself.",
            ))
    return entries


def has_cancellation_request(complaint):
    return complaint.events.filter(kind=Kind.CANCELLATION_REQUESTED).exists()


JOURNEY = (Status.RECEIVED, Status.UNDER_REVIEW)


def status_journey(complaint):
    """Received → Under Review → Resolved or Rejected, marking where the complaint is now."""
    final = complaint.status if complaint.status in (Status.RESOLVED, Status.REJECTED) else Status.RESOLVED
    steps = [*JOURNEY, final]
    current = steps.index(complaint.status) if complaint.status in steps else 0
    closing_pending = complaint.status not in (Status.RESOLVED, Status.REJECTED)
    return [
        {
            "label": "Resolved or Rejected" if (step == final and closing_pending) else Status(step).label,
            "state": "done" if index < current else ("current" if index == current else "upcoming"),
            "tone": status_tone(step),
        }
        for index, step in enumerate(steps)
    ]
