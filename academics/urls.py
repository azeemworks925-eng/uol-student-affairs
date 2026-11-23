from django.urls import path

from . import term_views, views

urlpatterns = [
    path("terms/", term_views.terms, name="super_admin_terms"),
    path("terms/add/", term_views.term_add, name="super_admin_term_add"),
    path("terms/<int:pk>/edit/", term_views.term_edit, name="super_admin_term_edit"),
    path("terms/<int:pk>/current/", term_views.term_make_current, name="super_admin_term_current"),
    path("terms/<int:pk>/clear/", term_views.term_clear_current, name="super_admin_term_clear"),
    path("structure/", views.structure, name="super_admin_structure"),
    path("structure/<str:kind>/add/", views.entry_add, name="super_admin_structure_add"),
    path("structure/<str:kind>/<int:pk>/edit/", views.entry_edit, name="super_admin_structure_edit"),
    path("structure/<str:kind>/<int:pk>/active/", views.entry_active, name="super_admin_structure_active"),
]
