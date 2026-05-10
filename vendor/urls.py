from django.urls import path
from .views import VendorOrderSummaryView, VendorOrdersExportView, ExportStatusView

urlpatterns = [
    path('orders/summary/', VendorOrderSummaryView.as_view(), name='vendor-order-summary'),
    path('orders/export/', VendorOrdersExportView.as_view(), name='vendor-order-export'),
    path('export/status/', ExportStatusView.as_view(), name='export-status'),
]