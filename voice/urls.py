from django.urls import path

from . import views

student_patterns = [
    path("", views.student_voice, name="student_voice"),
    path("<int:pk>/", views.student_voice_detail, name="student_voice_detail"),
]

advisor_patterns = [
    path("", views.advisor_voice, name="advisor_voice"),
    path("<int:pk>/", views.advisor_voice, name="advisor_voice_detail"),
    path("<int:pk>/answer/", views.advisor_answer, name="advisor_voice_answer"),
    path("<int:pk>/review/", views.advisor_review, name="advisor_voice_review"),
]

# Read-only: the Super Admin has no POST routes.
super_admin_patterns = [
    path("", views.super_admin_voice, name="super_admin_voice"),
    path("<int:pk>/", views.super_admin_voice, name="super_admin_voice_detail"),
]
