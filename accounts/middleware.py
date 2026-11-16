from django.shortcuts import redirect

from .models import StudentProfile

# Views a signed-in student may use before completing registration.
REGISTRATION_EXEMPT_URL_NAMES = {"student_register", "account_logout", "account_inactive"}


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
