from django.urls import path

from .views import CheckoutSessionCreateView


urlpatterns = [
    path('session/', CheckoutSessionCreateView.as_view(), name='checkout-session'),
]
