from django.conf import settings
from django.db import models

from tenants.mixins import TenantModel


class CheckoutSession(TenantModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="checkout_sessions",
    )
    cart = models.ForeignKey(
        "cart.Cart",
        on_delete=models.PROTECT,
        related_name="checkout_sessions",
    )
    idempotency_key = models.CharField(max_length=255, db_index=True)
    shipping_address = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(
                fields=["tenant", "status"],
                name="checkout_ch_tenant__83b44b_idx",
            ),
            models.Index(
                fields=["user", "status"],
                name="checkout_ch_user_id_6e9990_idx",
            ),
            models.Index(
                fields=["cart", "status"],
                name="checkout_ch_cart_id_3ba797_idx",
            ),
            models.Index(
                fields=["idempotency_key"],
                name="checkout_ch_idempot_de8bc9_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="unique_checkout_session_idempotency_per_tenant",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            self.tenant = self.cart.tenant
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Checkout session {self.pk} ({self.status})"
