from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail


@shared_task
def send_password_reset_email(user_id, uid, token):
    User = get_user_model()
    user = User.objects.get(pk=user_id)
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    reset_url = f'{frontend_url}/reset-password?uid={uid}&token={token}'

    send_mail(
        subject='Reset your password',
        message=(
            'Use the link below to reset your password:\n\n'
            f'{reset_url}'
        ),
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
        recipient_list=[user.email],
        fail_silently=False,
    )
