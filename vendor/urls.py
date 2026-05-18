from django.urls import path
from .views import (
    ExportStatusView,
    VendorDashboardSummaryView,
    VendorInventoryDetailView,
    VendorInventoryListView,
    VendorOrderSummaryView,
    VendorOrdersExportView,
)

urlpatterns = [
    path('dashboard/summary/', VendorDashboardSummaryView.as_view(), name='vendor-dashboard-summary'),
    path('inventory/', VendorInventoryListView.as_view(), name='vendor-inventory-list'),
    path('inventory/<int:pk>/', VendorInventoryDetailView.as_view(), name='vendor-inventory-detail'),
    path('orders/summary/', VendorOrderSummaryView.as_view(), name='vendor-order-summary'),
    path('orders/export/', VendorOrdersExportView.as_view(), name='vendor-order-export'),
    path('export/status/', ExportStatusView.as_view(), name='export-status'),
]
