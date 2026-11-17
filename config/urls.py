from django.contrib import admin
from django.urls import include, path

from accounts.views import admin_login_redirect

urlpatterns = [
    # Must precede admin.site.urls: replaces the admin's password login page.
    path("admin/login/", admin_login_redirect, name="admin_login_redirect"),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("student/complaints/", include("complaints.urls")),
    path("advisor/complaints/", include("complaints.advisor_urls")),
    path("super-admin/complaints/", include("complaints.admin_urls")),
    path("super-admin/complaint-categories/", include("complaints.category_urls")),
    path("", include("accounts.urls")),
]
