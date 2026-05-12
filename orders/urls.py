from django.urls import path

from .views import (
    VendorOrderConfirmView,
    VendorOrderMarkDeliveredView,
    VendorOrderMarkShippedView,
)


urlpatterns = [
    path(
        'vendor/orders/<int:order_id>/confirm/',
        VendorOrderConfirmView.as_view(),
        name='vendor-order-confirm',
    ),
    path(
        'vendor/orders/<int:order_id>/mark-shipped/',
        VendorOrderMarkShippedView.as_view(),
        name='vendor-order-mark-shipped',
    ),
    path(
        'vendor/orders/<int:order_id>/mark-delivered/',
        VendorOrderMarkDeliveredView.as_view(),
        name='vendor-order-mark-delivered',
    ),
]
