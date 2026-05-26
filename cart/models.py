from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

from tenants.middleware import get_current_tenant
from tenants.mixins import TenantModel


class Cart(TenantModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        MERGED = "merged", "Merged"
        CHECKED_OUT = "checked_out", "Checked out"
        ABANDONED = "abandoned", "Abandoned"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="carts",
        null=True,
        blank=True,
    )
    session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["session_key", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(user__isnull=False)
                    | (Q(session_key__isnull=False) & ~Q(session_key=""))
                ),
                name="cart_requires_user_or_session",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status="active", user__isnull=False),
                name="unique_active_cart_per_user",
            ),
            models.UniqueConstraint(
                fields=["session_key"],
                condition=(
                    Q(status="active")
                    & Q(session_key__isnull=False)
                    & ~Q(session_key="")
                ),
                name="unique_active_cart_per_session",
            ),
        ]

    @property
    def total_items(self):
        return self.items.aggregate(
            total=Coalesce(Sum("quantity"), 0, output_field=models.IntegerField()),
        )["total"]

    @property
    def subtotal(self):
        return sum(
            (item.line_total for item in self.items.all()),
            Decimal("0.00"),
        )

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            if self.user_id:
                self.tenant = self.user.tenant
            else:
                self.tenant = get_current_tenant()
        super().save(*args, **kwargs)

    def __str__(self):
        owner = self.user.email if self.user_id else self.session_key
        return f"Cart {self.pk} ({owner})"


class CartItem(TenantModel):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product_variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        default=1,
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["tenant", "cart"]),
            models.Index(fields=["tenant", "product_variant"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gte=1),
                name="cart_item_quantity_positive",
            ),
            models.UniqueConstraint(
                fields=["cart", "product_variant"],
                name="unique_variant_per_cart",
            ),
        ]

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def save(self, *args, **kwargs):
        if self.cart_id and self.tenant_id is None:
            self.tenant = self.cart.tenant
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity} x {self.product_variant}"
