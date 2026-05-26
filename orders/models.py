import uuid

from django.conf import settings
from django.dispatch import receiver
from django.db import models, transaction
from django_fsm import FSMField, transition
from django_fsm.signals import post_transition

from tenants.mixins import TenantModel

from notifications.tasks import send_order_shipped
from .tasks import send_order_status_email


def generate_order_number():
    return f"ORD-{uuid.uuid4().hex[:12].upper()}"


class Order(TenantModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    checkout_session = models.OneToOneField(
        "checkout.CheckoutSession",
        on_delete=models.PROTECT,
        related_name="order",
    )
    order_number = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        default=generate_order_number,
    )
    status = FSMField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        protected=True,
    )
    shipping_address = models.JSONField(default=dict)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["tenant", "status"],
                name="orders_orde_tenant__b18f3e_idx",
            ),
            models.Index(
                fields=["user", "status"],
                name="orders_orde_user_id_75d6ea_idx",
            ),
            models.Index(
                fields=["order_number"],
                name="orders_orde_order_n_0fb8b4_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            self.tenant = self.checkout_session.tenant
        super().save(*args, **kwargs)

    def __str__(self):
        return self.order_number

    @transition(field=status, source=Status.PENDING, target=Status.CONFIRMED)
    def confirm(self):
        pass

    @transition(field=status, source=Status.CONFIRMED, target=Status.PROCESSING)
    def mark_processing(self):
        pass

    @transition(field=status, source=Status.PROCESSING, target=Status.SHIPPED)
    def mark_shipped(self):
        pass

    @transition(field=status, source=Status.SHIPPED, target=Status.DELIVERED)
    def mark_delivered(self):
        pass

    @transition(field=status, source=Status.PENDING, target=Status.CANCELLED)
    def cancel(self):
        pass


class OrderItem(TenantModel):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product_variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    product_name = models.CharField(max_length=255)
    variant_label = models.CharField(max_length=255, blank=True)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["tenant", "order"],
                name="orders_orde_tenant__e8f030_idx",
            ),
            models.Index(
                fields=["tenant", "product_variant"],
                name="orders_orde_tenant__5eb05b_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.order_id and self.tenant_id is None:
            self.tenant = self.order.tenant
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"


class OrderEvent(TenantModel):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="events",
    )
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    transition = models.CharField(max_length=100)
    note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["tenant", "order"],
                name="orders_orde_tenant__ffc56c_idx",
            ),
            models.Index(
                fields=["tenant", "to_status"],
                name="orders_orde_tenant__5c4b3d_idx",
            ),
            models.Index(
                fields=["created_at"],
                name="orders_orde_created_e6ae50_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.order_id and self.tenant_id is None:
            self.tenant = self.order.tenant
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order} {self.from_status} -> {self.to_status}"


@receiver(post_transition, sender=Order)
def create_order_event(sender, instance, name, source, target, **kwargs):
    if not instance.pk:
        return

    OrderEvent.objects.create(
        order=instance,
        from_status=source or "",
        to_status=target,
        transition=name,
        tenant=instance.tenant,
    )
    transaction.on_commit(
        lambda: send_order_status_email.delay(instance.pk, target),
    )
    if target == Order.Status.SHIPPED:
        transaction.on_commit(
            lambda: send_order_shipped.delay(instance.pk),
        )
