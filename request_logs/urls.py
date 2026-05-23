from django.urls import path

from .views import AdminRequestLogListView


urlpatterns = [
    path(
        'logs/',
        AdminRequestLogListView.as_view(),
        name='admin-request-log-list',
    ),
]
