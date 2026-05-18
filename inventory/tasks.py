from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from .models import Inventory


@shared_task
def send_low_stock_alert(inventory_id):
    inventory = Inventory.all_objects.select_related(
        'vendor',
        'vendor__user',
        'product_variant',
        'product_variant__product',
    ).get(pk=inventory_id)
    product = inventory.product_variant.product
    recipients = []

    if inventory.vendor.contact_email:
        recipients.append(inventory.vendor.contact_email)
    if inventory.vendor.user.email:
        recipients.append(inventory.vendor.user.email)

    recipients = list(dict.fromkeys(recipients))

    if not recipients:
        return {
            'inventory_id': inventory.id,
            'status': 'skipped',
            'reason': 'No vendor email recipient configured.',
        }

    send_mail(
        subject=f'Low stock alert: {product.name}',
        message=(
            f'{product.name} is below its low stock threshold.\n\n'
            f'Current quantity: {inventory.quantity}\n'
            f'Low stock threshold: {inventory.low_stock_threshold}\n'
            f'Variant: {inventory.product_variant}'
        ),
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
        recipient_list=recipients,
        fail_silently=False,
    )

    return {
        'inventory_id': inventory.id,
        'status': 'sent',
        'recipients': recipients,
    }
