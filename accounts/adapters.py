"""
django-allauth adapters enforcing the portal's Google sign-in rules (DEC-010, DEC-200).

Flow for a verified Google identity:
1. An already linked Google account must still carry the same email as its portal user.
2. An unlinked Google account is linked to an existing portal account with the same
   email. This is how Super Admin-created Batch Advisor accounts are activated on their
   first sign-in (DEC-013). An account already linked to another Google identity is refused.
3. With no matching account, only a valid student email may sign up (DEC-011, DEC-012).
   Every other email is refused: staff accounts are created by the Super Admin only.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialAccount
from allauth.socialaccount.providers.base import AuthProcess

from . import identity
from .models import User


# Why a sign-in was refused, in words the person can act on (DEC-327).
DENIAL_MESSAGES = {
    "wrong_email": "Please use your UOL student email, like 12345678@student.uol.edu.pk",
    "not_uol_google": "This is not a UOL Google account. Please sign in with your UOL Google account.",
    "staff_not_set_up": "Your staff account hasn't been set up yet. Contact the Super Admin.",
    "deactivated": "Your account has been deactivated. If you think this is a mistake, contact the Super Admin.",
    "no_email": "Google did not provide an email address for this account.",
    "unverified": "Google has not verified the email address of this account.",
    "email_changed": "This Google account's email address no longer matches its portal account. "
                     "Please contact the Super Admin.",
    "already_linked": "This portal account is already linked to a different Google identity. "
                      "Please contact the Super Admin.",
    "linking": "Linking additional Google accounts is not supported.",
    "not_created": "This account could not be created. Please contact the Super Admin.",
}

# Which role each area of the site belongs to, so "back where you left off" never lands
# someone who chose a different account on a page their role cannot open.
ROLE_AREAS = {
    "/student/": User.Role.STUDENT,
    "/advisor/": User.Role.BATCH_ADVISOR,
    "/super-admin/": User.Role.SUPER_ADMIN,
    "/admin/": User.Role.SUPER_ADMIN,
}


def deny_sign_in(request, sociallogin, code, email=""):
    """Abort the sign-in and show why. Nothing is logged in or saved. "Try another account"
    keeps the page the person was trying to open."""
    response = render(request, "accounts/sign_in_denied.html", {
        "reason": DENIAL_MESSAGES[code],
        "reason_code": code,
        "email": email,
        "next_url": sociallogin.state.get("next") or "",
    }, status=403)
    raise ImmediateHttpResponse(response)


def page_allowed_for_role(url, role):
    """False when the path is inside another role's area of the site."""
    return all(role == owner for prefix, owner in ROLE_AREAS.items() if url.startswith(prefix))


class PortalAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # No local (password) sign-up. Students sign up only through Google.
        return False

    def get_login_redirect_url(self, request):
        return reverse("home")

    def is_safe_url(self, url):
        """`next` must be a path on this site. Anything else is dropped, so sign-in goes Home."""
        return bool(url) and url.startswith("/") and url_has_allowed_host_and_scheme(url, allowed_hosts=None)

    def post_login(self, request, user, *, redirect_url=None, **kwargs):
        if redirect_url and not (self.is_safe_url(redirect_url) and page_allowed_for_role(redirect_url, user.role)):
            redirect_url = None
        return super().post_login(request, user, redirect_url=redirect_url, **kwargs)


class PortalSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        if sociallogin.state.get("process") == AuthProcess.CONNECT:
            deny_sign_in(request, sociallogin, "linking")

        email = self._verified_email(request, sociallogin)

        if sociallogin.is_existing:
            if sociallogin.user.email != email:
                deny_sign_in(request, sociallogin, "email_changed", email)
            if not sociallogin.user.is_active:
                deny_sign_in(request, sociallogin, "deactivated", email)
            return

        user = User.objects.filter(email=email).first()
        if user is not None:
            if not user.is_active:
                deny_sign_in(request, sociallogin, "deactivated", email)
            if SocialAccount.objects.filter(user=user, provider=sociallogin.account.provider).exists():
                deny_sign_in(request, sociallogin, "already_linked", email)
            sociallogin.connect(request, user)
            return

        if not identity.is_student_email(email):
            code = "staff_not_set_up" if identity.is_staff_email(email) else "wrong_email"
            deny_sign_in(request, sociallogin, code, email)

    def _verified_email(self, request, sociallogin):
        claims = sociallogin.account.extra_data or {}
        email = identity.normalize_email(claims.get("email"))
        if not email:
            deny_sign_in(request, sociallogin, "no_email")
        if claims.get("email_verified") not in (True, "true", "True"):
            deny_sign_in(request, sociallogin, "unverified", email)
        # Only a listed demo address skips the hosted-domain check, and only when DEBUG is True.
        if settings.UOL_GOOGLE_REQUIRE_HOSTED_DOMAIN and not identity.is_demo_staff_email(email):
            hosted_domain = identity.normalize_email(claims.get("hd"))
            allowed = {identity.normalize_email(d) for d in settings.UOL_GOOGLE_ALLOWED_HOSTED_DOMAINS}
            if not hosted_domain or hosted_domain not in allowed:
                looks_like_uol = identity.is_student_email(email) or identity.is_staff_email(email)
                deny_sign_in(request, sociallogin, "not_uol_google" if looks_like_uol else "wrong_email", email)
        return email

    def is_open_for_signup(self, request, sociallogin):
        return identity.is_student_email(getattr(sociallogin.user, "email", ""))

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.email = identity.normalize_email(user.email)
        user.role = User.Role.STUDENT
        # The full name is collected at registration (DEC-201), not taken from Google.
        user.first_name = user.last_name = ""
        return user

    def save_user(self, request, sociallogin, form=None):
        user = sociallogin.user
        user.role = User.Role.STUDENT
        user.set_unusable_password()
        try:
            user.full_clean()
        except ValidationError:
            deny_sign_in(request, sociallogin, "not_created", user.email)
        return super().save_user(request, sociallogin, form)

    def validate_disconnect(self, account, accounts):
        raise ValidationError("Google sign-in cannot be removed from a portal account.")
