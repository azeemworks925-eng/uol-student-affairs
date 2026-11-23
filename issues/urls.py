from django.urls import path

from . import views

# Before <reference>/: references look like CI-2026-00012, never "new".
student_patterns = [
    path("", views.student_section_issues, name="student_section_issues"),
    path("new/", views.student_issue_new, name="student_issue_new"),
    path("<str:reference>/", views.student_issue_detail, name="student_issue_detail"),
    path("<str:reference>/support/", views.student_issue_support, name="student_issue_support"),
]

advisor_patterns = [
    path("", views.advisor_issues, name="advisor_issues"),
    path("<str:reference>/", views.advisor_issue_detail, name="advisor_issue_detail"),
    path("<str:reference>/review/", views.advisor_issue_review, name="advisor_issue_review"),
    path("<str:reference>/respond/", views.advisor_issue_respond, name="advisor_issue_respond"),
    path("<str:reference>/resolve/", views.advisor_issue_resolve, name="advisor_issue_resolve"),
]

# Read-only: the Super Admin has no POST routes.
super_admin_patterns = [
    path("", views.super_admin_issues, name="super_admin_issues"),
    path("<str:reference>/", views.super_admin_issue_detail, name="super_admin_issue_detail"),
]
