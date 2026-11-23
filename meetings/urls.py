from django.urls import path

from . import views

student_patterns = [
    path("", views.student_meetings, name="student_meetings"),
    path("month/", views.student_month, name="student_meetings_month"),
    path("<int:pk>/", views.student_meeting_detail, name="student_meeting_detail"),
    path("<int:pk>/accept/", views.student_accept, name="student_meeting_accept"),
    path("<int:pk>/decline/", views.student_decline, name="student_meeting_decline"),
    path("<int:pk>/cancel/", views.student_cancel, name="student_meeting_cancel"),
]

advisor_patterns = [
    path("", views.advisor_meetings, name="advisor_meetings"),
    path("schedule/", views.advisor_schedule, name="advisor_meeting_schedule"),
    path("month/", views.advisor_month, name="advisor_meetings_month"),
    path("<int:pk>/", views.advisor_meeting_detail, name="advisor_meeting_detail"),
    path("<int:pk>/confirm/", views.advisor_confirm, name="advisor_meeting_confirm"),
    path("<int:pk>/suggest/", views.advisor_suggest, name="advisor_meeting_suggest"),
    path("<int:pk>/decline/", views.advisor_decline, name="advisor_meeting_decline"),
    path("<int:pk>/cancel/", views.advisor_cancel, name="advisor_meeting_cancel"),
]

# Read-only: the Super Admin has no POST routes.
super_admin_patterns = [
    path("", views.super_admin_meetings, name="super_admin_meetings"),
]
