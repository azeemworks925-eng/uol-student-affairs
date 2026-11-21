from django.urls import path

from . import advisor_views

# Batch Advisor complaints workspace (Complaints Part 3).
urlpatterns = [
    path("", advisor_views.workspace_view, name="advisor_complaints"),
    # Before <reference>/: references look like CMP-2026-00012, never "go" or "next".
    path("go/", advisor_views.go_to_reference, name="advisor_complaint_go"),
    path("next/", advisor_views.next_complaint, name="advisor_complaint_next"),
    path("<str:reference>/", advisor_views.workspace_view, name="advisor_complaint_detail"),
    path("<str:reference>/respond/", advisor_views.respond, name="advisor_complaint_respond"),
    path("<str:reference>/status/", advisor_views.update_status, name="advisor_complaint_status"),
]
