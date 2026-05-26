from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework_simplejwt.tokens import RefreshToken

from cart.models import Cart
from cart.services import CartService
from notifications.tasks import send_password_reset_email

from .serializers import CustomTokenObtainPairSerializer
from .tasks import send_email_verification_email
from .token_blacklist import blacklist_token_in_redis
from .tokens import email_verification_token_generator


User = get_user_model()


class AuthService:
    @staticmethod
    def token_pair_for_user(user):
        refresh = CustomTokenObtainPairSerializer.get_token(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }

    @staticmethod
    def merge_guest_cart(request, user):
        session = getattr(request, 'session', None)
        session_key = getattr(session, 'session_key', None)
        if not session_key:
            return

        guest_cart = Cart.objects.filter(
            session_key=session_key,
            status=Cart.Status.ACTIVE,
        ).first()
        if not guest_cart:
            return

        tenant = getattr(request, 'tenant', None) or user.tenant
        user_cart = CartService.get_or_create_cart(
            SimpleNamespace(user=user, tenant=tenant),
        )
        CartService.merge_carts(guest_cart, user_cart)

    @classmethod
    def complete_registration(cls, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token_generator.make_token(user)
        send_email_verification_email.delay(user.id, uid, token)
        return cls.token_pair_for_user(user)

    @classmethod
    def register_user(cls, serializer):
        user = serializer.save()
        token_pair = cls.complete_registration(user)
        return user, token_pair

    @staticmethod
    def verify_email(user):
        if user.is_email_verified:
            return False

        user.is_email_verified = True
        user.save(update_fields=['is_email_verified'])
        return True

    @staticmethod
    def logout(refresh_token, access_token=None):
        token = RefreshToken(refresh_token)
        blacklist_token_in_redis(token)
        if access_token:
            blacklist_token_in_redis(access_token)
        token.blacklist()

    @staticmethod
    def request_password_reset(email):
        normalized_email = User.objects.normalize_email(email)
        user = User.objects.filter(
            email=normalized_email,
            is_active=True,
        ).first()
        if user:
            token = default_token_generator.make_token(user)
            send_password_reset_email.delay(user.id, token)

    @staticmethod
    def reset_password(user, new_password):
        user.set_password(new_password)
        user.save(update_fields=['password'])

    @staticmethod
    def update_profile(serializer):
        return serializer.save()
