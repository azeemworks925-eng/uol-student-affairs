from urllib.parse import urlencode

from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from .forms import StudentRegistrationForm
from .models import StudentProfile, User
from .permissions import batch_advisor_required, student_required, super_admin_required
from .services import register_student

ROLE_HOME_URL_NAMES = {
    User.Role.STUDENT: "student_home",
    User.Role.BATCH_ADVISOR: "advisor_home",
    User.Role.SUPER_ADMIN: "super_admin_home",
}


def home(request):
    """Direct each user to their role's area. There is no role selector (DEC-200)."""
    if not request.user.is_authenticated:
        return redirect("account_login")
    return redirect(ROLE_HOME_URL_NAMES[request.user.role])


@student_required
@require_http_methods(["GET", "POST"])
def student_register(request):
    if StudentProfile.objects.filter(user=request.user).exists():
        # Registration is one-time; corrections are made by the Super Admin (DEC-202).
        return redirect("home")

    form = StudentRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        register_student(request.user, **form.cleaned_data)
        return redirect("home")
    return render(request, "accounts/register.html", {"form": form})


# Placeholder role areas. Dashboard interfaces wait for the agreed design direction.

@student_required
def student_home(request):
    return render(request, "accounts/role_home.html", {"profile": request.user.student_profile})


@batch_advisor_required
def advisor_home(request):
    assignments = request.user.advisor_assignments.select_related("semester", "section")
    return render(request, "accounts/role_home.html", {"assignments": assignments})


@super_admin_required
def super_admin_home(request):
    return render(request, "accounts/role_home.html")


def admin_login_redirect(request):
    """The Django admin has no password login: send it to the shared Google login page."""
    next_url = request.GET.get("next") or reverse("admin:index")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse("admin:index")
    return HttpResponseRedirect(f"{reverse('account_login')}?{urlencode({'next': next_url})}")
