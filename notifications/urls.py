from django.urls import path

from . import views

urlpatterns = [
    path("", views.notification_list, name="notifications"),
    path("<int:pk>/open/", views.notification_open, name="notification_open"),
    path("read-all/", views.notification_mark_all_read, name="notifications_mark_all_read"),
]
