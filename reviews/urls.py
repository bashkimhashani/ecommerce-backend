from django.urls import path

from .views import CustomerReviewView, PurchasedItemsView, VendorReviewListView

urlpatterns = [
    path("", CustomerReviewView.as_view(), name="customer-review-create"),
    path("purchased-items/", PurchasedItemsView.as_view(), name="purchased-items"),
    path("vendor/", VendorReviewListView.as_view(), name="vendor-review-list"),
]
