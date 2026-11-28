"""
Role-based navigation for the application shell (DESIGN_PLAN.md section 3; DEC-304, DEC-306).

Destinations whose module has not been built yet stay listed here with url_name=None but are
not rendered: the shell shows only pages that exist, and an item reappears as soon as its
url_name is set. Access control is never decided here: views enforce roles (accounts.permissions).
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse

from .models import User
from .representation import Cohort, cohort_is_active, current_representative


@dataclass(frozen=True)
class NavItem:
    label: str
    icon: str
    url_name: str | None = None
    query: dict | None = None
    kwargs: dict | None = None
    # Other views that belong to this destination, so it stays marked as current there.
    also_current: tuple = ()
    # Shown only to the current CR or GR of a cohort.
    representative_only: bool = False
    # Whether it is one of the student's phone bottom tabs (DEC-304, DEC-324).
    bottom_tab: bool = True

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
                    also_current=("student_meetings_month", "student_meetings_week", "student_meeting_detail")),
            NavItem("Section issues", "hand", "student_section_issues", representative_only=True, bottom_tab=False,
                    also_current=("student_issue_new", "student_issue_detail")),
        ]),
    ],
    User.Role.BATCH_ADVISOR: [
        (None, [
            NavItem("Overview", "grid", "advisor_home"),
            NavItem("Complaints", "file", "advisor_complaints", also_current=ADVISOR_COMPLAINT_VIEWS),
            NavItem("Collective Issues", "hand", "advisor_issues", also_current=("advisor_issue_detail",)),
            NavItem("Student Voice", "voice", "advisor_voice",
                    also_current=("advisor_voice_detail", "advisor_voice_answer", "advisor_voice_review")),
            NavItem("Meetings", "calendar", "advisor_meetings",
                    also_current=("advisor_meetings_month", "advisor_meetings_week", "advisor_meeting_detail", "advisor_meeting_schedule",
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
            NavItem("Collective Issues", "hand", "super_admin_issues", also_current=("super_admin_issue_detail",)),
            NavItem("Student Voice", "voice", "super_admin_voice", also_current=("super_admin_voice_detail",)),
            NavItem("Meetings", "calendar", "super_admin_meetings",
                    also_current=("super_admin_meetings_month", "super_admin_meetings_week", "super_admin_meeting_detail")),
        ]),
        ("People", [
            NavItem("Students", "user", "super_admin_students",
                    also_current=("super_admin_student_detail", "super_admin_student_changes", "super_admin_student_edit",
                                  "super_admin_student_active")),
            NavItem("Staff", "users", "super_admin_staff",
                    also_current=("super_admin_staff_detail", "super_admin_staff_name", "super_admin_staff_active",
                                  "super_admin_staff_assignment_add", "super_admin_staff_assignment_remove")),
            NavItem("CR/GR Management", "badge", "super_admin_representatives",
                    also_current=("super_admin_representatives_appoint", "super_admin_representatives_replace")),
        ]),
        ("Configuration", [
            NavItem("Academic Structure", "layers", "super_admin_structure",
                    also_current=("super_admin_structure_add", "super_admin_structure_edit", "super_admin_structure_active")),
            NavItem("Academic Terms", "calendar", "super_admin_terms",
                    also_current=("super_admin_term_add", "super_admin_term_edit", "super_admin_term_current",
                                  "super_admin_term_clear")),
            NavItem("Complaint Categories", "tags", "super_admin_categories", also_current=CATEGORY_VIEWS),
        ]),
    ],
}


# The top bar's create actions: existing pages only, each with its icon chip's pastel.
# Rule (Polish v2): exactly one action is a labelled button; two or more become a "+ New" menu.
@dataclass(frozen=True)
class CreateAction:
    label: str
    icon: str
    url_name: str
    query: str = ""
    pastel: str = "mint"
    # The label of the direct button when this is a role's only action.
    button_label: str = ""

    def resolve(self):
        return {"label": self.label, "button_label": self.button_label or self.label, "icon": self.icon,
                "pastel": self.pastel, "url": reverse(self.url_name) + self.query}


CREATE_ACTIONS = {
    User.Role.STUDENT: [
        CreateAction("New complaint", "file", "student_complaint_new", pastel="sky"),
        CreateAction("Voice submission", "voice", "student_voice", "?new=1", pastel="lavender"),
        CreateAction("Request meeting", "calendar", "student_meetings", "?new=1", pastel="mint"),
    ],
    User.Role.BATCH_ADVISOR: [CreateAction("Schedule meeting", "calendar", "advisor_meeting_schedule", pastel="mint")],
    User.Role.SUPER_ADMIN: [CreateAction("Add Batch Advisor", "user", "super_admin_staff", "?new=1", pastel="mint")],
}
# The current CR or GR of an active cohort only.
RAISE_ISSUE = CreateAction("Raise a section issue", "hand", "student_issue_new", pastel="amber")


def create_actions(user, period=None):
    """The resolved create actions for this user, in menu order."""
    actions = list(CREATE_ACTIONS.get(user.role, []))
    if period is not None and cohort_is_active(Cohort.of(period)):
        actions.append(RAISE_ISSUE)
    return [action.resolve() for action in actions]


def create_control(actions):
    """{"button": the one action, or None; "menu": the actions when there are two or more}."""
    if len(actions) == 1:
        return {"button": actions[0], "menu": []}
    return {"button": None, "menu": actions}


def _resolve(item, current_url_name):
    return {
        "label": item.label,
        "icon": item.icon,
        "url": item.url(),
        "current": bool(item.url_name) and current_url_name in (item.url_name, *item.also_current),
        "bottom_tab": item.bottom_tab,
    }


def navigation(request):
    """Template context processor: the signed-in user's navigation groups."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated) or user.role not in NAVIGATION:
        return {}
    match = getattr(request, "resolver_match", None)
    current = match.view_name if match else None
    # Read from the database on every request, so a former CR or GR loses the links at once.
    period = current_representative(user) if user.is_student else None
    groups = []
    for heading, items in NAVIGATION[user.role]:
        built = [_resolve(item, current) for item in items
                 if item.url_name and (period is not None or not item.representative_only)]
        if built:  # a group with nothing built yet is left out, heading included
            groups.append({"heading": heading, "items": built})
    items = [i for g in groups for i in g["items"]]
    actions = create_actions(user, period)
    return {
        "sa_nav": groups,
        "sa_nav_items": items,
        "sa_nav_bottom": [i for i in items if i["bottom_tab"]],
        "sa_nav_current": next((i for i in items if i["current"]), None),
        "sa_new_menu": actions,
        "sa_create": create_control(actions),
        "sa_show_theme_toggle": getattr(settings, "SHOW_THEME_TOGGLE", True),
    }
