from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.student_register, name="student_register"),
    path("student/", views.student_home, name="student_home"),
    path("advisor/", views.advisor_home, name="advisor_home"),
    path("super-admin/", views.super_admin_home, name="super_admin_home"),
]
