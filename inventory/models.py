from django.db import models
from catalog.models import ProductVariant
from tenants.mixins import TenantModel
from vendor.models import VendorProfile


class Inventory(TenantModel):
    """
    Inventory management for vendor product variants.
    """
    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='inventory_items',
    )
    vendor = models.ForeignKey(
        VendorProfile,
        on_delete=models.CASCADE,
        related_name='inventory_items',
    )
    quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['vendor']),
            models.Index(fields=['tenant']),
            models.Index(fields=['product_variant']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'product_variant'],
                name='unique_inventory_variant_per_tenant',
            ),
        ]

    @property
    def is_active(self):
        return self.product_variant.product.status == 'active'

    @property
    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    def __str__(self):
        return f'{self.product_variant} - {self.quantity} in stock'
