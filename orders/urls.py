from django.urls import path

from .views import VendorOrderConfirmView


urlpatterns = [
    path(
        'vendor/orders/<int:order_id>/confirm/',
        VendorOrderConfirmView.as_view(),
        name='vendor-order-confirm',
    ),
]
