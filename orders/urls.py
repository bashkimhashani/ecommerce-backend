from django.urls import path

from .views import (
    CustomerOrderCancelView,
    CustomerOrderDetailView,
    CustomerOrderListView,
    VendorOrderConfirmView,
    VendorOrderListView,
    VendorOrderMarkDeliveredView,
    VendorOrderMarkShippedView,
)

urlpatterns = [
    path(
        "orders/",
        CustomerOrderListView.as_view(),
        name="customer-order-list",
    ),
    path(
        "orders/<str:order_number>/",
        CustomerOrderDetailView.as_view(),
        name="customer-order-detail",
    ),
    path(
        "orders/<int:order_id>/cancel/",
        CustomerOrderCancelView.as_view(),
        name="customer-order-cancel",
    ),
    path(
        "vendor/orders/",
        VendorOrderListView.as_view(),
        name="vendor-order-list",
    ),
    path(
        "vendor/orders/<int:order_id>/confirm/",
        VendorOrderConfirmView.as_view(),
        name="vendor-order-confirm",
    ),
    path(
        "vendor/orders/<int:order_id>/mark-shipped/",
        VendorOrderMarkShippedView.as_view(),
        name="vendor-order-mark-shipped",
    ),
    path(
        "vendor/orders/<int:order_id>/mark-delivered/",
        VendorOrderMarkDeliveredView.as_view(),
        name="vendor-order-mark-delivered",
    ),
]
