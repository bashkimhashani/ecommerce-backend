from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_encode

from .email_logging import create_email_log
from .models import EmailLog


ORDER_CONFIRMATION_TASK = 'notifications.tasks.send_order_confirmation'
ORDER_SHIPPED_TASK = 'notifications.tasks.send_order_shipped'
PASSWORD_RESET_TASK = 'notifications.tasks.send_password_reset_email'


@shared_task(autoretry_for=(Exception,), retry_backoff=True)
def send_order_confirmation(order_id):
    from orders.models import Order

    order = (
        Order.all_objects.select_related('user')
        .prefetch_related('items')
        .get(pk=order_id)
    )
    recipient = order.user.email
    subject = f'Order confirmation: {order.order_number}'

    if not recipient:
        create_email_log(
            task_name=ORDER_CONFIRMATION_TASK,
            recipient=recipient,
            subject=subject,
            status=EmailLog.Status.SKIPPED,
            tenant=order.tenant,
            related_object_id=order.id,
            message='No customer email recipient configured.',
        )
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
    plain_message = strip_tags(html_message)

    send_logged_email(
        task_name=ORDER_CONFIRMATION_TASK,
        recipient=recipient,
        subject=subject,
        plain_message=plain_message,
        html_message=html_message,
        tenant=order.tenant,
        related_object_id=order.id,
    )

    return {
        'order_id': order.id,
        'order_number': order.order_number,
        'status': 'sent',
        'recipient': recipient,
    }


@shared_task(autoretry_for=(Exception,), retry_backoff=True)
def send_order_shipped(order_id):
    from orders.models import Order

    order = (
        Order.all_objects.select_related('user')
        .prefetch_related('items')
        .get(pk=order_id)
    )
    recipient = order.user.email
    subject = f'Order shipped: {order.order_number}'

    if not recipient:
        create_email_log(
            task_name=ORDER_SHIPPED_TASK,
            recipient=recipient,
            subject=subject,
            status=EmailLog.Status.SKIPPED,
            tenant=order.tenant,
            related_object_id=order.id,
            message='No customer email recipient configured.',
        )
        return {
            'order_id': order.id,
            'status': 'skipped',
            'reason': 'No customer email recipient configured.',
        }

    html_message = render_to_string(
        'emails/order_shipped.html',
        {
            'order': order,
            'items': list(order.items.all()),
            'customer_name': customer_name(order.user),
            'shipping_address': normalize_shipping_address(
                order.shipping_address,
            ),
        },
    )
    plain_message = strip_tags(html_message)

    send_logged_email(
        task_name=ORDER_SHIPPED_TASK,
        recipient=recipient,
        subject=subject,
        plain_message=plain_message,
        html_message=html_message,
        tenant=order.tenant,
        related_object_id=order.id,
    )

    return {
        'order_id': order.id,
        'order_number': order.order_number,
        'status': 'sent',
        'recipient': recipient,
    }


@shared_task(autoretry_for=(Exception,), retry_backoff=True)
def send_password_reset_email(user_id, token):
    User = get_user_model()
    user = User.objects.get(pk=user_id)
    recipient = user.email
    subject = 'Reset your password'

    if not recipient:
        create_email_log(
            task_name=PASSWORD_RESET_TASK,
            recipient=recipient,
            subject=subject,
            status=EmailLog.Status.SKIPPED,
            tenant=getattr(user, 'tenant', None),
            related_object_id=user.id,
            message='No user email recipient configured.',
        )
        return {
            'user_id': user.id,
            'status': 'skipped',
            'reason': 'No user email recipient configured.',
        }

    reset_url = password_reset_url(user, token)
    html_message = render_to_string(
        'emails/password_reset.html',
        {
            'customer_name': customer_name(user),
            'reset_url': reset_url,
        },
    )
    plain_message = strip_tags(html_message)

    send_logged_email(
        task_name=PASSWORD_RESET_TASK,
        recipient=recipient,
        subject=subject,
        plain_message=plain_message,
        html_message=html_message,
        tenant=getattr(user, 'tenant', None),
        related_object_id=user.id,
    )

    return {
        'user_id': user.id,
        'status': 'sent',
        'recipient': recipient,
    }


def send_logged_email(
    *,
    task_name,
    recipient,
    subject,
    plain_message,
    html_message,
    tenant=None,
    related_object_id='',
):
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            recipient_list=[recipient],
            fail_silently=False,
            html_message=html_message,
        )
    except Exception as exc:
        create_email_log(
            task_name=task_name,
            recipient=recipient,
            subject=subject,
            status=EmailLog.Status.FAILED,
            tenant=tenant,
            related_object_id=related_object_id,
            message=plain_message,
            error=str(exc),
        )
        raise

    create_email_log(
        task_name=task_name,
        recipient=recipient,
        subject=subject,
        status=EmailLog.Status.SENT,
        tenant=tenant,
        related_object_id=related_object_id,
        message=plain_message,
    )


def customer_name(user):
    full_name = user.get_full_name().strip()
    return full_name or user.email


def password_reset_url(user, token):
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return f'{frontend_url}/reset-password?uid={uid}&token={token}'


def normalize_shipping_address(shipping_address):
    if not shipping_address:
        return {}

    return {
        'full_name': shipping_address.get('full_name', ''),
        'line1': (
            shipping_address.get('line1')
            or shipping_address.get('address_line1')
            or ''
        ),
        'line2': (
            shipping_address.get('line2')
            or shipping_address.get('address_line2')
            or ''
        ),
        'city': shipping_address.get('city', ''),
        'postal_code': shipping_address.get('postal_code', ''),
        'country': shipping_address.get('country', ''),
    }
