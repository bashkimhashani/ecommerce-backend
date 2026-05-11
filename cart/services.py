import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from redis.exceptions import RedisError

from tenants.middleware import get_current_tenant

from .cache import CartRedisCache
from .models import Cart, CartItem


class CartService:
    @classmethod
    def get_serialized_cart(cls, request):
        user = getattr(request, 'user', None)

        if not user or not user.is_authenticated:
            session_key = cls._get_or_create_session_key(request)
            cached_cart = cls._get_cached_cart(session_key)
            if cached_cart is not None:
                return cached_cart

        cart = cls.get_or_create_cart(request)
        payload = CartRedisCache.serialize_cart(cart)
        return cls._json_safe(payload)

    @classmethod
    @transaction.atomic
    def get_or_create_cart(cls, request):
        user = getattr(request, 'user', None)
        tenant = getattr(request, 'tenant', None) or get_current_tenant()

        if user and user.is_authenticated:
            return cls._get_or_create_user_cart(user, tenant)

        session_key = cls._get_or_create_session_key(request)
        return cls._get_or_create_guest_cart(session_key, tenant)

    @classmethod
    def _get_or_create_user_cart(cls, user, tenant):
        cart, _ = Cart.objects.select_for_update().get_or_create(
            user=user,
            status=Cart.Status.ACTIVE,
            defaults={
                'tenant': tenant or user.tenant,
            },
        )
        return cart

    @classmethod
    def _get_or_create_guest_cart(cls, session_key, tenant):
        cart, _ = Cart.objects.select_for_update().get_or_create(
            session_key=session_key,
            status=Cart.Status.ACTIVE,
            defaults={
                'tenant': tenant,
            },
        )
        cls._store_cart_after_commit(cart)
        return cart

    @staticmethod
    def _get_or_create_session_key(request):
        session = getattr(request, 'session', None)
        if session is None:
            raise ValueError('Cart requests require session middleware.')

        if not session.session_key:
            session.create()

        return session.session_key

    @classmethod
    @transaction.atomic
    def add_item(cls, cart, product_variant, quantity):
        product_variant = type(product_variant).objects.select_for_update().get(
            pk=product_variant.pk,
        )
        item = (
            CartItem.objects.select_for_update()
            .filter(cart=cart, product_variant=product_variant)
            .first()
        )
        current_quantity = item.quantity if item else 0
        requested_quantity = current_quantity + quantity

        if requested_quantity > product_variant.stock_quantity:
            raise ValueError('Requested quantity exceeds available stock.')

        if item:
            item.quantity = requested_quantity
            item.save(update_fields=['quantity', 'updated_at'])
            cls._store_cart_after_commit(cart)
            return item

        item = CartItem.objects.create(
            cart=cart,
            product_variant=product_variant,
            quantity=quantity,
            unit_price=product_variant.variant_price,
            tenant=cart.tenant,
        )
        cls._store_cart_after_commit(cart)
        return item

    @classmethod
    @transaction.atomic
    def update_item_quantity(cls, item, quantity):
        product_variant = type(item.product_variant).objects.select_for_update().get(
            pk=item.product_variant_id,
        )
        item = CartItem.objects.select_for_update().get(pk=item.pk)

        if quantity > product_variant.stock_quantity:
            raise ValueError('Requested quantity exceeds available stock.')

        item.quantity = quantity
        item.save(update_fields=['quantity', 'updated_at'])
        cls._store_cart_after_commit(item.cart)
        return item

    @classmethod
    @transaction.atomic
    def remove_item(cls, item):
        item = CartItem.objects.select_for_update().get(pk=item.pk)
        cart = item.cart
        item.delete()
        cls._store_cart_after_commit(cart)

    @classmethod
    def _store_cart_after_commit(cls, cart):
        if not cart.session_key:
            return

        transaction.on_commit(lambda: cls._store_cart(cart.pk))

    @staticmethod
    def _store_cart(cart_id):
        try:
            cart = Cart.objects.prefetch_related(
                'items__product_variant__product',
            ).get(pk=cart_id)
            CartRedisCache.store_cart(cart)
        except (Cart.DoesNotExist, RedisError):
            return

    @staticmethod
    def _get_cached_cart(session_key):
        try:
            return CartRedisCache.get_cart(session_key)
        except (json.JSONDecodeError, RedisError):
            return None

    @staticmethod
    def _json_safe(payload):
        return json.loads(json.dumps(payload, cls=DjangoJSONEncoder))
