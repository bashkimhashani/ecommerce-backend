from django.contrib import admin

from .models import ProductReview


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "vendor", "user", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("product__name", "vendor__store_name", "user__email", "comment")
