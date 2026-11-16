"""Shared test data and a Google sign-in simulator."""

import time
from unittest import mock
from urllib.parse import parse_qs, urlparse

import jwt
from django.urls import reverse

from academics.models import Batch, Section, Semester
from accounts.models import AdvisorAssignment, StudentProfile, User

STUDENT_EMAIL = "12345678@student.uol.edu.pk"
OTHER_STUDENT_EMAIL = "87654321@student.uol.edu.pk"
ADVISOR_EMAIL = "advisor@uol.edu.pk"
OTHER_ADVISOR_EMAIL = "advisor2@uol.edu.pk"
SUPER_ADMIN_EMAIL = "head@uol.edu.pk"

GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
GOOGLE_PROVIDERS = {
    "google": {
        "SCOPE": ["openid", "email", "profile"],
        "AUTH_PARAMS": {"prompt": "select_account"},
        "OAUTH_PKCE_ENABLED": True,
        "APP": {"client_id": GOOGLE_CLIENT_ID, "secret": "test-secret", "key": ""},
    }
}
# Signature checks are skipped for tokens fetched directly from Google over TLS (OIDC
# Core 3.1.3.7), so the key is irrelevant; issuer, audience and expiry are still checked.
_TEST_SIGNING_KEY = "test-signing-key-that-is-long-enough-for-hs256"


def make_academics():
    return {
        "batch": Batch.objects.create(name="Fall 2024"),
        "semester": Semester.objects.create(number=4),
        "section": Section.objects.create(name="A"),
        "other_semester": Semester.objects.create(number=5),
        "other_section": Section.objects.create(name="B"),
    }


def make_student(email=STUDENT_EMAIL, *, academics=None, semester=None, section=None, full_name="Test Student"):
    user = User.objects.create_user(email=email, full_name=full_name)
    if academics:
        StudentProfile.objects.create(
            user=user,
            batch=academics["batch"],
            semester=semester or academics["semester"],
            section=section or academics["section"],
        )
    return user


def make_advisor(email=ADVISOR_EMAIL, *, assignments=(), full_name="Test Advisor"):
    advisor = User.objects.create_user(email=email, role=User.Role.BATCH_ADVISOR, full_name=full_name)
    for semester, section in assignments:
        AdvisorAssignment.objects.create(advisor=advisor, semester=semester, section=section)
    return advisor


def make_super_admin(email=SUPER_ADMIN_EMAIL):
    return User.objects.create_superuser(email=email, full_name="Head of Batch Advisors")


def google_claims(email, *, sub="google-sub-1", email_verified=True, hd="__from_email__", **overrides):
    """ID token claims as Google issues them for a Workspace account."""
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": GOOGLE_CLIENT_ID,
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "name": "Google Display Name",
        "iat": now,
        "exp": now + 3600,
    }
    if hd == "__from_email__":
        hd = email.rpartition("@")[2].lower()
    if hd is not None:
        claims["hd"] = hd
    claims.update(overrides)
    return claims


def start_google_sign_in(client, next_url=None):
    """POST to the sign-in endpoint and return the state Google would echo back."""
    response = client.post(reverse("google_login"), {"next": next_url} if next_url else {})
    assert response.status_code == 302, response.status_code
    location = urlparse(response["Location"])
    assert location.netloc == "accounts.google.com", response["Location"]
    return parse_qs(location.query)["state"][0]


def complete_google_sign_in(client, claims, state):
    """Simulate Google's redirect back with an authorization code, stubbing only the HTTP token exchange."""
    token_response = {
        "access_token": "test-access-token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "id_token": jwt.encode(claims, _TEST_SIGNING_KEY, algorithm="HS256"),
    }
    with mock.patch(
        "allauth.socialaccount.providers.oauth2.client.OAuth2Client.get_access_token",
        return_value=token_response,
    ):
        return client.get(reverse("google_callback"), {"code": "test-code", "state": state})


def google_sign_in(client, claims, next_url=None):
    return complete_google_sign_in(client, claims, start_google_sign_in(client, next_url))
