from django.urls import path
from .views import (
    ExportStatusView,
    VendorAnalyticsAskView,
    VendorDashboardSummaryView,
    VendorInventoryDetailView,
    VendorInventoryListView,
    VendorLatestReportView,
    VendorOrderSummaryView,
    VendorOrdersExportView,
)

urlpatterns = [
    path(
        'reports/latest/',
        VendorLatestReportView.as_view(),
        name='vendor-report-latest',
    ),
    path(
        'analytics/ask/',
        VendorAnalyticsAskView.as_view(),
        name='vendor-analytics-ask',
    ),
    path(
        'dashboard/summary/',
        VendorDashboardSummaryView.as_view(),
        name='vendor-dashboard-summary',
    ),
    path(
        'inventory/',
        VendorInventoryListView.as_view(),
        name='vendor-inventory-list',
    ),
    path(
        'inventory/<int:pk>/',
        VendorInventoryDetailView.as_view(),
        name='vendor-inventory-detail',
    ),
    path(
        'orders/summary/',
        VendorOrderSummaryView.as_view(),
        name='vendor-order-summary',
    ),
    path('orders/export/', VendorOrdersExportView.as_view(), name='vendor-order-export'),
    path('export/status/', ExportStatusView.as_view(), name='export-status'),
]
