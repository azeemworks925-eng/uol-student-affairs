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

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialAccount
from allauth.socialaccount.providers.base import AuthProcess

from . import identity
from .models import User


def deny_sign_in(request, reason):
    """Abort the sign-in and show why. Nothing is logged in or saved."""
    response = render(request, "accounts/sign_in_denied.html", {"reason": reason}, status=403)
    raise ImmediateHttpResponse(response)


class PortalAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # No local (password) sign-up. Students sign up only through Google.
        return False

    def get_login_redirect_url(self, request):
        return reverse("home")


class PortalSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        if sociallogin.state.get("process") == AuthProcess.CONNECT:
            deny_sign_in(request, "Linking additional Google accounts is not supported.")

        email = self._verified_email(request, sociallogin)

        if sociallogin.is_existing:
            if sociallogin.user.email != email:
                deny_sign_in(
                    request,
                    "This Google account's email address no longer matches its portal account. "
                    "Please contact the Super Admin.",
                )
            return

        user = User.objects.filter(email=email).first()
        if user is not None:
            if SocialAccount.objects.filter(user=user, provider=sociallogin.account.provider).exists():
                deny_sign_in(
                    request,
                    "This portal account is already linked to a different Google identity. "
                    "Please contact the Super Admin.",
                )
            sociallogin.connect(request, user)
            return

        if not identity.is_student_email(email):
            deny_sign_in(
                request,
                "No portal account exists for this email address. Students must sign in with "
                f"their eight-digit SAP ID address at @{identity.STUDENT_EMAIL_DOMAIN}. "
                "Batch Advisor accounts are created by the Super Admin.",
            )

    def _verified_email(self, request, sociallogin):
        claims = sociallogin.account.extra_data or {}
        email = identity.normalize_email(claims.get("email"))
        if not email:
            deny_sign_in(request, "Google did not provide an email address for this account.")
        if claims.get("email_verified") not in (True, "true", "True"):
            deny_sign_in(request, "Google has not verified the email address of this account.")
        if settings.UOL_GOOGLE_REQUIRE_HOSTED_DOMAIN:
            hosted_domain = identity.normalize_email(claims.get("hd"))
            allowed = {identity.normalize_email(d) for d in settings.UOL_GOOGLE_ALLOWED_HOSTED_DOMAINS}
            if not hosted_domain or hosted_domain not in allowed:
                deny_sign_in(request, "Please sign in with your UOL Google account.")
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
            deny_sign_in(request, "This account could not be created. Please contact the Super Admin.")
        return super().save_user(request, sociallogin, form)

    def validate_disconnect(self, account, accounts):
        raise ValidationError("Google sign-in cannot be removed from a portal account.")
