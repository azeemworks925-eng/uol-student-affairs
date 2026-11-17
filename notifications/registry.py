"""
Registered notification types (DEC-270). Each type declares the model its source records must be
and the routes a notification of that type may open. notifications.services.notify refuses
anything else, and opening re-checks the destination against this list.

Only the two complaint producers of Part 4 are registered. Future DEC-270 producers (official
Student Voice answers; meeting confirmation, rescheduling and cancellation; new CR/GR issues)
add an entry here and a producer in their own module; their recipients are decided with them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationType:
    source_model: str  # model label, lower case, for example "complaints.complaintevent"
    destinations: frozenset  # allowed route names


REGISTRY = {
    "complaint.status_changed": NotificationType(
        source_model="complaints.complaintevent", destinations=frozenset({"student_complaint_detail"})
    ),
    "complaint.response": NotificationType(
        source_model="complaints.complaintevent", destinations=frozenset({"student_complaint_detail"})
    ),
}


def get_type(event_type):
    return REGISTRY.get(event_type)


def is_allowed_destination(event_type, url_name):
    notification_type = REGISTRY.get(event_type)
    return notification_type is not None and url_name in notification_type.destinations
