from django.urls import path
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)
from .views import (
    CustomTokenObtainPairView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetView,
    RegisterView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('password-reset/', PasswordResetView.as_view(), name='password-reset'),
    path(
        'password-reset/confirm/',
        PasswordResetConfirmView.as_view(),
        name='password-reset-confirm',
    ),
    path('me/', MeView.as_view(), name='me'),
]
