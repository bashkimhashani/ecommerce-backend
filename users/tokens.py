from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing


EMAIL_VERIFICATION_SALT = 'users.email_verification'
EMAIL_VERIFICATION_MAX_AGE = 60 * 60 * 24


def make_email_verification_token(user):
    return signing.dumps(
        {
            'user_id': user.pk,
            'email': user.email,
        },
        salt=EMAIL_VERIFICATION_SALT,
    )


def get_user_from_email_verification_token(token):
    max_age = getattr(
        settings,
        'EMAIL_VERIFICATION_TOKEN_MAX_AGE',
        EMAIL_VERIFICATION_MAX_AGE,
    )
    data = signing.loads(
        token,
        salt=EMAIL_VERIFICATION_SALT,
        max_age=max_age,
    )
    User = get_user_model()
    return User.objects.get(
        pk=data['user_id'],
        email=data['email'],
        is_active=True,
    )
