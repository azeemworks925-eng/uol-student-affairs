from django.urls import path

from . import views

# Student pages (Complaints Part 2). Staff complaint pages come in later parts.
urlpatterns = [
    path("", views.complaint_list, name="student_complaints"),
    path("new/", views.complaint_new, name="student_complaint_new"),
    path("<str:reference>/", views.complaint_detail, name="student_complaint_detail"),
    path("<str:reference>/information/", views.complaint_add_information, name="student_complaint_add_information"),
    path(
        "<str:reference>/still-not-resolved/",
        views.complaint_still_not_resolved,
        name="student_complaint_still_not_resolved",
    ),
    path(
        "<str:reference>/cancellation/",
        views.complaint_request_cancellation,
        name="student_complaint_request_cancellation",
    ),
]
