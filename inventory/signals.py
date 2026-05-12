from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Inventory
from .tasks import send_low_stock_alert


@receiver(pre_save, sender=Inventory)
def remember_previous_inventory_quantity(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_quantity = None
        instance._previous_low_stock_threshold = None
        return

    previous = Inventory.all_objects.filter(pk=instance.pk).only(
        'quantity',
        'low_stock_threshold',
    ).first()

    instance._previous_quantity = previous.quantity if previous else None
    instance._previous_low_stock_threshold = (
        previous.low_stock_threshold if previous else None
    )


@receiver(post_save, sender=Inventory)
def queue_low_stock_alert(sender, instance, created, **kwargs):
    if created:
        return

    previous_quantity = getattr(instance, '_previous_quantity', None)
    previous_threshold = getattr(
        instance,
        '_previous_low_stock_threshold',
        None,
    )

    if previous_quantity is None or previous_threshold is None:
        return

    was_low_stock = previous_quantity < previous_threshold
    is_low_stock = instance.quantity < instance.low_stock_threshold

    if is_low_stock and not was_low_stock:
        send_low_stock_alert.delay(instance.id)
