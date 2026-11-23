from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from .models import StudentProfile

# Views a signed-in student may use before completing registration.
REGISTRATION_EXEMPT_URL_NAMES = {"student_register", "account_logout", "account_inactive"}

# A small marker meaning "this browser had a session" (DEC-327). Its value is always "1": it
# holds no personal data and grants no access.
SESSION_MARKER_COOKIE = "sa_had_session"
SESSION_MARKER_MAX_AGE = 7 * 24 * 60 * 60  # after a week away, it is simply a fresh visit


class SessionMarkerMiddleware:
    """
    Tells a timed-out session apart from a normal sign-out:
    - signed in: the marker is set;
    - signed out on purpose: the marker is cleared;
    - marker present but no longer signed in: the session timed out, so the sign-in page says so
      once and then clears the marker.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        has_marker = request.COOKIES.get(SESSION_MARKER_COOKIE) == "1"
        was_signed_in = request.user.is_authenticated
        request.session_timed_out = has_marker and not was_signed_in

        response = self.get_response(request)

        if request.user.is_authenticated:
            if not has_marker:
                response.set_cookie(
                    SESSION_MARKER_COOKIE, "1", max_age=SESSION_MARKER_MAX_AGE, httponly=True,
                    samesite="Lax", secure=settings.SESSION_COOKIE_SECURE,
                )
        elif has_marker and (was_signed_in or self._on_sign_in_page(request)):
            response.delete_cookie(SESSION_MARKER_COOKIE, samesite="Lax")
        if request.session_timed_out:
            self._return_to_the_form_page(request, response)
        return response

    @staticmethod
    def _on_sign_in_page(request):
        match = getattr(request, "resolver_match", None)
        return match is not None and match.url_name == "account_login"

    @staticmethod
    def _return_to_the_form_page(request, response):
        """A form sent after the timeout cannot be replayed with a GET, so `next` becomes the
        same-site page the form was on instead of its POST-only address."""
        login_url = reverse("account_login")
        if request.method != "POST" or response.status_code != 302 or not response["Location"].startswith(f"{login_url}?"):
            return
        referer = urlsplit(request.META.get("HTTP_REFERER", ""))
        if referer.netloc != request.get_host():
            response["Location"] = login_url
            return
        page = f"{referer.path}?{referer.query}" if referer.query else referer.path
        response["Location"] = f"{login_url}?{urlencode({'next': page})}"


class StudentRegistrationMiddleware:
    """
    Send signed-in students who have not completed registration (DEC-201) to the
    registration page, whatever URL they request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = request.user
        if not (user.is_authenticated and user.is_student):
            return None
        match = request.resolver_match
        if match is not None and match.url_name in REGISTRATION_EXEMPT_URL_NAMES:
            return None
        if StudentProfile.objects.filter(user=user).exists():
            return None
        return redirect("student_register")
