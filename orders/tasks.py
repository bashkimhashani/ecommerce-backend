from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task(autoretry_for=(Exception,), retry_backoff=True)
def send_order_status_email(order_id, status):
    from .models import Order

    order = Order.objects.select_related('user').get(pk=order_id)
    status_label = dict(Order.Status.choices).get(status, status)

    send_mail(
        subject=f'Order {order.order_number} is now {status_label}',
        message=(
            f'Your order {order.order_number} status has changed to '
            f'{status_label}.'
        ),
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
        recipient_list=[order.user.email],
        fail_silently=False,
    )
