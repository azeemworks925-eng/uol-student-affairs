from django.urls import path

from . import representative_views as reps
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.student_register, name="student_register"),
    path("student/", views.student_home, name="student_home"),
    path("advisor/", views.advisor_home, name="advisor_home"),
    path("super-admin/", views.super_admin_home, name="super_admin_home"),
    # CR/GR representation (Collective Issues CI-1). Changes are POST-only; there is no remove route.
    path("advisor/representatives/", reps.advisor_index, name="advisor_representatives"),
    path("advisor/representatives/<str:cohort>/appoint/", reps.advisor_appoint, name="advisor_representatives_appoint"),
    path("advisor/representatives/<str:cohort>/replace/<str:post>/", reps.advisor_replace, name="advisor_representatives_replace"),
    path("super-admin/representatives/", reps.admin_index, name="super_admin_representatives"),
    path("super-admin/representatives/<str:cohort>/appoint/", reps.admin_appoint, name="super_admin_representatives_appoint"),
    path("super-admin/representatives/<str:cohort>/replace/<str:post>/", reps.admin_replace, name="super_admin_representatives_replace"),
]
