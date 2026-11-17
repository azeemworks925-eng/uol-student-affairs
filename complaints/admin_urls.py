from django.urls import path

from . import admin_views

# Super Admin complaints workspace (Complaints Part 4 Stage 1).
urlpatterns = [
    path("", admin_views.workspace_view, name="super_admin_complaints"),
    path("<str:reference>/", admin_views.workspace_view, name="super_admin_complaint_detail"),
    path("<str:reference>/respond/", admin_views.respond, name="super_admin_complaint_respond"),
    path("<str:reference>/status/", admin_views.update_status, name="super_admin_complaint_status"),
    path("<str:reference>/owner/", admin_views.assign_owner, name="super_admin_complaint_owner"),
]
