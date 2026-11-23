from django.urls import path

from . import people_views as views

urlpatterns = [
    path("students/", views.students, name="super_admin_students"),
    path("students/history/", views.student_changes, name="super_admin_student_changes"),
    path("students/<int:pk>/", views.student_detail, name="super_admin_student_detail"),
    path("students/<int:pk>/edit/", views.student_edit, name="super_admin_student_edit"),
    path("students/<int:pk>/active/", views.student_active, name="super_admin_student_active"),
]
