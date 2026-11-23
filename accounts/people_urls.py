from django.urls import path

from . import people_views as views
from . import staff_views as staff

urlpatterns = [
    path("staff/", staff.staff, name="super_admin_staff"),
    path("staff/<int:pk>/", staff.staff_detail, name="super_admin_staff_detail"),
    path("staff/<int:pk>/name/", staff.staff_name, name="super_admin_staff_name"),
    path("staff/<int:pk>/active/", staff.staff_active, name="super_admin_staff_active"),
    path("staff/<int:pk>/assignments/add/", staff.assignment_add, name="super_admin_staff_assignment_add"),
    path("staff/<int:pk>/assignments/<int:assignment_pk>/remove/", staff.assignment_remove,
         name="super_admin_staff_assignment_remove"),
    path("students/", views.students, name="super_admin_students"),
    path("students/history/", views.student_changes, name="super_admin_student_changes"),
    path("students/<int:pk>/", views.student_detail, name="super_admin_student_detail"),
    path("students/<int:pk>/edit/", views.student_edit, name="super_admin_student_edit"),
    path("students/<int:pk>/active/", views.student_active, name="super_admin_student_active"),
]
