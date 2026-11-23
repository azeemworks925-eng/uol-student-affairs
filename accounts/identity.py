"""
Email identity rules for UOL Student Affairs.

- Every email is normalized to lowercase in full (see PortalUserManager.normalize_email).
- Students: exactly an eight-digit SAP ID at @student.uol.edu.pk (DEC-011).
- Staff (Batch Advisors and the Super Admin): an official UOL staff domain, configured
  through settings.UOL_STAFF_EMAIL_DOMAINS (default "uol.edu.pk"; see open item O2).
"""

import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

STUDENT_EMAIL_DOMAIN = "student.uol.edu.pk"
_STUDENT_EMAIL_RE = re.compile(r"^(?P<sap_id>\d{8})@student\.uol\.edu\.pk$")


def normalize_email(email):
    return (email or "").strip().lower()


def email_domain(email):
    _, _, domain = normalize_email(email).rpartition("@")
    return domain


def extract_sap_id(email):
    """Return the SAP ID from a valid student email, or None."""
    match = _STUDENT_EMAIL_RE.fullmatch(normalize_email(email))
    return match.group("sap_id") if match else None


def is_student_email(email):
    return extract_sap_id(email) is not None


def staff_email_domains():
    return {normalize_email(d) for d in settings.UOL_STAFF_EMAIL_DOMAINS if d.strip()}


def demo_staff_emails():
    """
    The laptop-only demo staff addresses (DEC-327), in the order listed. Empty unless DEBUG is
    True, so the setting has no effect on a production server. A student-domain or malformed
    address is never a demo staff address.
    """
    if not settings.DEBUG:
        return []
    emails = []
    for email in map(normalize_email, settings.DEMO_STAFF_EMAILS):
        try:
            validate_email(email)
        except ValidationError:
            continue
        if email_domain(email) != STUDENT_EMAIL_DOMAIN and email not in emails:
            emails.append(email)
    return emails


def is_demo_staff_email(email):
    return normalize_email(email) in demo_staff_emails()


def is_staff_email(email):
    domain = email_domain(email)
    if not domain or domain == STUDENT_EMAIL_DOMAIN:
        return False
    return domain in staff_email_domains() or is_demo_staff_email(email)
