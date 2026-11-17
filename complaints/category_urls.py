from django.urls import path

from . import category_views as views

# Super Admin category management (Complaints Part 4 Stage 2). Changes are POST-only; there is
# no delete route.
urlpatterns = [
    path("", views.index, name="super_admin_categories"),
    path("new/", views.category_create, name="super_admin_category_create"),
    path("<int:pk>/", views.detail, name="super_admin_category_detail"),
    path("<int:pk>/rename/", views.category_rename, name="super_admin_category_rename"),
    path("<int:pk>/active/", views.category_active, name="super_admin_category_active"),
    path("<int:pk>/move/", views.category_move, name="super_admin_category_move"),
    path("<int:pk>/subcategories/new/", views.subcategory_create, name="super_admin_subcategory_create"),
    path("<int:pk>/subcategories/<int:sub_pk>/rename/", views.subcategory_rename, name="super_admin_subcategory_rename"),
    path("<int:pk>/subcategories/<int:sub_pk>/active/", views.subcategory_active, name="super_admin_subcategory_active"),
    path("<int:pk>/subcategories/<int:sub_pk>/move/", views.subcategory_move, name="super_admin_subcategory_move"),
]
