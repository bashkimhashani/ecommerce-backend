import uuid

from django.conf import settings
from django.db import models

from tenants.mixins import TenantModel


def generate_order_number():
    return f'ORD-{uuid.uuid4().hex[:12].upper()}'


class Order(TenantModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        PROCESSING = 'processing', 'Processing'
        SHIPPED = 'shipped', 'Shipped'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='orders',
    )
    checkout_session = models.OneToOneField(
        'checkout.CheckoutSession',
        on_delete=models.PROTECT,
        related_name='order',
    )
    order_number = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        default=generate_order_number,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    shipping_address = models.JSONField(default=dict)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['order_number']),
        ]

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            self.tenant = self.checkout_session.tenant
        super().save(*args, **kwargs)

    def __str__(self):
        return self.order_number


class OrderItem(TenantModel):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
    )
    product_variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='order_items',
    )
    product_name = models.CharField(max_length=255)
    variant_label = models.CharField(max_length=255, blank=True)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['tenant', 'order']),
            models.Index(fields=['tenant', 'product_variant']),
        ]

    def save(self, *args, **kwargs):
        if self.order_id and self.tenant_id is None:
            self.tenant = self.order.tenant
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.quantity} x {self.product_name}'
