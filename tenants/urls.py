from django.urls import path

from .views import TenantRegisterView

urlpatterns = [
    path("register/", TenantRegisterView.as_view(), name="tenant-register"),
]
