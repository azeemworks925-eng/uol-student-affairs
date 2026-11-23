from django.urls import path

from . import views

student_patterns = [
    path("<str:reference>/", views.student_issue_detail, name="student_issue_detail"),
    path("<str:reference>/support/", views.student_issue_support, name="student_issue_support"),
]
