from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from complaints.analytics import build_overview
from complaints.presentation import student_updates
from complaints.workspace import advisor_cohort_counts, cohort_value

from .forms import StudentRegistrationForm
from .identity import extract_sap_id
from .models import StudentProfile, User
from .permissions import batch_advisor_required, student_required, super_admin_required
from .presentation import first_name, greeting, personal_summary
from .services import AlreadyRegistered, register_student

ROLE_HOME_URL_NAMES = {
    User.Role.STUDENT: "student_home",
    User.Role.BATCH_ADVISOR: "advisor_home",
    User.Role.SUPER_ADMIN: "super_admin_home",
}


def home(request):
    """Signed-out visitors see the landing page; everyone else goes to their role's area.
    There is no role selector (DEC-200)."""
    if not request.user.is_authenticated:
        return render(request, "accounts/landing.html")
    return redirect(ROLE_HOME_URL_NAMES[request.user.role])


@student_required
@require_http_methods(["GET", "POST"])
def student_register(request):
    if StudentProfile.objects.filter(user=request.user).exists():
        # Registration is one-time; corrections are made by the Super Admin (DEC-202).
        return redirect("home")

    form = StudentRegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            register_student(request.user, **form.cleaned_data)
        except (IntegrityError, AlreadyRegistered):
            # A concurrent submission registered first (seen under the locks, or kept out by the
            # one-profile-per-user constraint), so the student is already registered.
            pass
        except ValidationError as error:
            # An entry was deactivated after the form was shown (checked under the cohort lock).
            form.add_error(None, error.messages)
            return render(request, "accounts/register.html",
                          {"form": form, "sap_id": extract_sap_id(request.user.email)}, status=400)
        return redirect("home")
    return render(request, "accounts/register.html", {"form": form, "sap_id": extract_sap_id(request.user.email)})


def cohort_label(batch, semester, section):
    """The exact cohort, spelled out: "Fall 2024 · Semester 4 · Section A" (DEC-205)."""
    return f"{batch} · {semester} · {section}"


# Quick Access: three separate actions (DEC-282, DEC-303). An action whose module is not built
# yet keeps url_name None and is not shown; it appears once its url_name is set.
QUICK_ACCESS = [
    {"label": "Submit a complaint", "description": "Raise a problem with your Batch Advisor", "icon": "plus", "url_name": "student_complaint_new", "primary": True},
    {"label": "Student Voice", "description": "An idea, a question or feedback", "icon": "voice", "url_name": None},
    {"label": "My meetings", "description": "Request or review meetings", "icon": "calendar", "url_name": None},
]


def quick_access():
    return [{**item, "url": reverse(item["url_name"])} for item in QUICK_ACCESS if item["url_name"]]


@student_required
def student_home(request):
    profile = request.user.student_profile
    # The student's latest staff updates on their complaints (status changes and responses),
    # newest first. Student Voice and meetings will add their own updates when they are built.
    updates = student_updates(request.user)
    return render(request, "accounts/student_home.html", {
        "profile": profile,
        "today": timezone.localdate(),
        "greeting": greeting(),
        "first_name": first_name(request.user),
        "cohort_label": cohort_label(profile.batch, profile.semester, profile.section),
        "summary": personal_summary([update.headline for update in updates]),
        "updates": updates,
        "quick_access": quick_access(),
    })


@batch_advisor_required
def advisor_home(request):
    assignments = list(request.user.advisor_assignments.select_related("batch", "semester", "section"))
    workspace = reverse("advisor_complaints")
    counts = advisor_cohort_counts(request.user)
    for a in assignments:
        value = cohort_value(a.batch_id, a.semester_id, a.section_id)
        # P3-8: each card opens the complaints workspace filtered to this exact cohort.
        a.complaints_url = f"{workspace}?{urlencode({'cohort': value})}"
        a.counts = counts.get(value, {"open": 0, "resolved_recently": 0, "total": 0})
    return render(request, "accounts/advisor_home.html", {"assignments": assignments})


@super_admin_required
def super_admin_home(request):
    # The three DEC-281 analytics (Complaints Part 4 Stage 4b). Suppression is decided in
    # complaints.analytics; the template receives displayable values only (DEC-318).
    return render(request, "accounts/super_admin_home.html", {
        "analytics": build_overview(request.user),
        "term_admin_url": reverse("admin:academics_academicterm_changelist"),
    })


def admin_login_redirect(request):
    """The Django admin has no password login: send it to the shared Google login page."""
    next_url = request.GET.get("next") or reverse("admin:index")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse("admin:index")
    return HttpResponseRedirect(f"{reverse('account_login')}?{urlencode({'next': next_url})}")
