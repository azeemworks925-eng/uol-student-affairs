"""
Role-based navigation for the application shell (DESIGN_PLAN.md section 3; DEC-304, DEC-306).

Destinations whose module has not been built yet stay listed here with url_name=None but are
not rendered: the shell shows only pages that exist, and an item reappears as soon as its
url_name is set. Access control is never decided here: views enforce roles (accounts.permissions).
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from django.urls import reverse

from .models import User


@dataclass(frozen=True)
class NavItem:
    label: str
    icon: str
    url_name: str | None = None
    query: dict | None = None
    kwargs: dict | None = None
    # Other views that belong to this destination, so it stays marked as current there.
    also_current: tuple = ()

    def url(self):
        if not self.url_name:
            return None
        base = reverse(self.url_name, kwargs=self.kwargs)
        return f"{base}?{urlencode(self.query)}" if self.query else base


STUDENT_COMPLAINT_VIEWS = (
    "student_complaint_new",
    "student_complaint_detail",
    "student_complaint_add_information",
    "student_complaint_still_not_resolved",
    "student_complaint_request_cancellation",
)

ADVISOR_COMPLAINT_VIEWS = ("advisor_complaint_detail", "advisor_complaint_respond", "advisor_complaint_status")
SUPER_ADMIN_COMPLAINT_VIEWS = (
    "super_admin_complaint_detail",
    "super_admin_complaint_respond",
    "super_admin_complaint_status",
    "super_admin_complaint_owner",
)

CATEGORY_VIEWS = (
    "super_admin_category_create",
    "super_admin_category_detail",
    "super_admin_category_rename",
    "super_admin_category_active",
    "super_admin_category_move",
    "super_admin_subcategory_create",
    "super_admin_subcategory_rename",
    "super_admin_subcategory_active",
    "super_admin_subcategory_move",
)

# (group heading or None, items)
NAVIGATION = {
    User.Role.STUDENT: [
        (None, [
            NavItem("Home", "home", "student_home"),
            NavItem("Complaints", "file", "student_complaints", also_current=STUDENT_COMPLAINT_VIEWS),
            NavItem("Student Voice", "voice", "student_voice", also_current=("student_voice_detail",)),
            NavItem("Meetings", "calendar", "student_meetings",
                    also_current=("student_meetings_month", "student_meeting_detail")),
        ]),
    ],
    User.Role.BATCH_ADVISOR: [
        (None, [
            NavItem("Overview", "grid", "advisor_home"),
            NavItem("Complaints", "file", "advisor_complaints", also_current=ADVISOR_COMPLAINT_VIEWS),
            NavItem("Collective Issues", "hand"),
            NavItem("Student Voice", "voice", "advisor_voice",
                    also_current=("advisor_voice_detail", "advisor_voice_answer", "advisor_voice_review")),
            NavItem("Meetings", "calendar", "advisor_meetings",
                    also_current=("advisor_meetings_month", "advisor_meeting_detail", "advisor_meeting_schedule",
                                  "advisor_meeting_confirm", "advisor_meeting_suggest", "advisor_meeting_decline",
                                  "advisor_meeting_cancel")),
            NavItem("Representatives", "users", "advisor_representatives",
                    also_current=("advisor_representatives_appoint", "advisor_representatives_replace")),
            NavItem("Statistics", "chart"),
        ]),
    ],
    # No separate Statistics destination for the Super Admin (DEC-306).
    User.Role.SUPER_ADMIN: [
        ("Oversight", [
            NavItem("Overview", "grid", "super_admin_home"),
            NavItem("Complaints", "file", "super_admin_complaints", also_current=SUPER_ADMIN_COMPLAINT_VIEWS),
            NavItem("Collective Issues", "hand"),
            NavItem("Student Voice", "voice", "super_admin_voice", also_current=("super_admin_voice_detail",)),
            NavItem("Meetings", "calendar", "super_admin_meetings"),
        ]),
        ("People", [
            NavItem("Students", "user", "admin:accounts_studentprofile_changelist"),
            NavItem("Batch Advisors", "users", "admin:accounts_user_changelist", {"role__exact": User.Role.BATCH_ADVISOR}),
            NavItem("CR/GR Management", "badge", "super_admin_representatives",
                    also_current=("super_admin_representatives_appoint", "super_admin_representatives_replace")),
        ]),
        ("Configuration", [
            NavItem("Academic Structure", "layers", "admin:app_list", kwargs={"app_label": "academics"}),
            NavItem("Complaint Categories", "tags", "super_admin_categories", also_current=CATEGORY_VIEWS),
        ]),
    ],
}


# The top bar's "+ New" menu: existing pages only.
NEW_MENU = {
    User.Role.STUDENT: [
        ("New complaint", "file", "student_complaint_new"),
        ("Student Voice", "voice", "student_voice"),
        ("Request meeting", "calendar", "student_meetings"),
    ],
    User.Role.BATCH_ADVISOR: [("Schedule meeting", "calendar", "advisor_meeting_schedule")],
    User.Role.SUPER_ADMIN: [("Add Batch Advisor", "user", "admin:accounts_user_add")],
}


def _resolve(item, current_url_name):
    return {
        "label": item.label,
        "icon": item.icon,
        "url": item.url(),
        "current": bool(item.url_name) and current_url_name in (item.url_name, *item.also_current),
    }


def navigation(request):
    """Template context processor: the signed-in user's navigation groups."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated) or user.role not in NAVIGATION:
        return {}
    match = getattr(request, "resolver_match", None)
    current = match.view_name if match else None
    groups = []
    for heading, items in NAVIGATION[user.role]:
        built = [_resolve(item, current) for item in items if item.url_name]
        if built:  # a group with nothing built yet is left out, heading included
            groups.append({"heading": heading, "items": built})
    items = [i for g in groups for i in g["items"]]
    return {
        "sa_nav": groups,
        "sa_nav_items": items,
        "sa_nav_current": next((i for i in items if i["current"]), None),
        "sa_new_menu": [{"label": label, "icon": icon, "url": reverse(name)} for label, icon, name in NEW_MENU[user.role]],
    }
