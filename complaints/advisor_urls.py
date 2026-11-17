from django.urls import path

from . import advisor_views

# Batch Advisor complaints workspace (Complaints Part 3).
urlpatterns = [
    path("", advisor_views.workspace_view, name="advisor_complaints"),
    path("<str:reference>/", advisor_views.workspace_view, name="advisor_complaint_detail"),
    path("<str:reference>/respond/", advisor_views.respond, name="advisor_complaint_respond"),
    path("<str:reference>/status/", advisor_views.update_status, name="advisor_complaint_status"),
]
