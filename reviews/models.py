from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from tenants.mixins import TenantModel


class ProductReview(TenantModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_reviews",
    )
    order_item = models.OneToOneField(
        "orders.OrderItem",
        on_delete=models.CASCADE,
        related_name="review",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=120, blank=True)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "vendor"]),
            models.Index(fields=["tenant", "product"]),
            models.Index(fields=["tenant", "user"]),
            models.Index(fields=["tenant", "rating"]),
        ]

    def save(self, *args, **kwargs):
        if self.order_item_id and self.tenant_id is None:
            self.tenant = self.order_item.tenant or self.order_item.order.tenant
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} review by {self.user}"
