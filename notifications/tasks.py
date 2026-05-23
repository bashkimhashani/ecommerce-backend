from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags


@shared_task
def send_order_confirmation(order_id):
    from orders.models import Order

    order = (
        Order.all_objects.select_related('user')
        .prefetch_related('items')
        .get(pk=order_id)
    )
    recipient = order.user.email

    if not recipient:
        return {
            'order_id': order.id,
            'status': 'skipped',
            'reason': 'No customer email recipient configured.',
        }

    html_message = render_to_string(
        'emails/order_confirmation.html',
        {
            'order': order,
            'items': list(order.items.all()),
            'customer_name': customer_name(order.user),
        },
    )

    send_mail(
        subject=f'Order confirmation: {order.order_number}',
        message=strip_tags(html_message),
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
        recipient_list=[recipient],
        fail_silently=False,
        html_message=html_message,
    )

    return {
        'order_id': order.id,
        'order_number': order.order_number,
        'status': 'sent',
        'recipient': recipient,
    }


def customer_name(user):
    full_name = user.get_full_name().strip()
    return full_name or user.email
