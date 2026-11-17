"""Shared complaint test data, built on the account test helpers."""

from accounts.tests.helpers import (  # noqa: F401  (re-exported for the complaint tests)
    OTHER_STUDENT_EMAIL,
    STUDENT_EMAIL,
    cohort,
    make_academics,
    make_advisor,
    make_student,
    make_super_admin,
)
from complaints import services
from complaints.models import ComplaintCategory, ComplaintSubcategory


def make_categories():
    """Categories created by the test, independent of the seeded rows."""
    academic = ComplaintCategory.objects.create(name="Test Academic", position=10)
    return {
        "academic": academic,
        "exams": ComplaintSubcategory.objects.create(category=academic, name="Exams"),
        "other": ComplaintCategory.objects.create(name="Test Other", position=11),
    }


def submit(student, category, **overrides):
    data = {"title": "Lab timetable clash", "description": "Two labs are scheduled at the same time."}
    data.update(overrides)
    return services.submit_complaint(student, category=category, **data)
