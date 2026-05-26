from django.urls import path

from .views import (
    CheckoutSessionAddressUpdateView,
    CheckoutSessionCreateView,
    CheckoutSessionPaymentIntentView,
)

urlpatterns = [
    path("session/", CheckoutSessionCreateView.as_view(), name="checkout-session"),
    path(
        "session/<int:session_id>/address/",
        CheckoutSessionAddressUpdateView.as_view(),
        name="checkout-session-address",
    ),
    path(
        "session/<int:session_id>/payment-intent/",
        CheckoutSessionPaymentIntentView.as_view(),
        name="checkout-session-payment-intent",
    ),
]
