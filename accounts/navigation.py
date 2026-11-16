"""
Role-based navigation for the application shell (DESIGN_PLAN.md section 3; DEC-304, DEC-306).

Destinations whose module has not been built yet are listed with url=None and rendered as
unavailable, so the information architecture is visible without linking to pages that do
not exist. Access control is never decided here: views enforce roles (accounts.permissions).
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

    def url(self):
        if not self.url_name:
            return None
        base = reverse(self.url_name)
        return f"{base}?{urlencode(self.query)}" if self.query else base


# (group heading or None, items)
NAVIGATION = {
    User.Role.STUDENT: [
        (None, [
            NavItem("Home", "home", "student_home"),
            NavItem("Complaints", "file"),
            NavItem("Student Voice", "voice"),
            NavItem("Meetings", "calendar"),
        ]),
    ],
    User.Role.BATCH_ADVISOR: [
        (None, [
            NavItem("Overview", "grid", "advisor_home"),
            NavItem("Complaints", "file"),
            NavItem("Collective Issues", "hand"),
            NavItem("Student Voice", "voice"),
            NavItem("Meetings", "calendar"),
            NavItem("Representatives", "users"),
            NavItem("Statistics", "chart"),
        ]),
    ],
    # No separate Statistics destination for the Super Admin (DEC-306).
    User.Role.SUPER_ADMIN: [
        ("Oversight", [
            NavItem("Overview", "grid", "super_admin_home"),
            NavItem("Complaints", "file"),
            NavItem("Collective Issues", "hand"),
            NavItem("Calendar", "calendar"),
        ]),
        ("People", [
            NavItem("Students", "user", "admin:accounts_studentprofile_changelist"),
            NavItem("Batch Advisors", "users", "admin:accounts_user_changelist", {"role__exact": User.Role.BATCH_ADVISOR}),
            NavItem("CR/GR Management", "badge"),
        ]),
        ("Configuration", [
            NavItem("Academic Structure", "layers", "admin:app_list", None),
            NavItem("Complaint Categories", "tags"),
        ]),
    ],
}


def _resolve(item, current_url_name):
    if item.url_name == "admin:app_list":
        url = reverse("admin:app_list", kwargs={"app_label": "academics"})
    else:
        url = item.url()
    return {
        "label": item.label,
        "icon": item.icon,
        "url": url,
        "current": bool(item.url_name) and item.url_name == current_url_name,
    }


def navigation(request):
    """Template context processor: the signed-in user's navigation groups."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated) or user.role not in NAVIGATION:
        return {}
    match = getattr(request, "resolver_match", None)
    current = match.view_name if match else None
    groups = [
        {"heading": heading, "items": [_resolve(item, current) for item in items]}
        for heading, items in NAVIGATION[user.role]
    ]
    return {"sa_nav": groups, "sa_nav_items": [i for g in groups for i in g["items"]]}
