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
            cls._invalidate_cart_after_commit(cart)
            return item

        item = CartItem.objects.create(
            cart=cart,
            product_variant=product_variant,
            quantity=quantity,
            unit_price=product_variant.variant_price,
            tenant=cart.tenant,
        )
        cls._invalidate_cart_after_commit(cart)
        return item

    @staticmethod
    def get_item(cart, item_id):
        return cart.items.filter(pk=item_id).first()

    @classmethod
    def update_item_for_cart(cls, cart, item_id, quantity):
        item = cls.get_item(cart, item_id)
        if item is None:
            return None
        return cls.update_item_quantity(item=item, quantity=quantity)

    @classmethod
    def remove_item_from_cart(cls, cart, item_id):
        item = cls.get_item(cart, item_id)
        if item is None:
            return False
        cls.remove_item(item)
        return True

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
        cls._invalidate_cart_after_commit(item.cart)
        return item

    @classmethod
    @transaction.atomic
    def remove_item(cls, item):
        item = CartItem.objects.select_for_update().get(pk=item.pk)
        cart = item.cart
        item.delete()
        cls._invalidate_cart_after_commit(cart)

    @classmethod
    @transaction.atomic
    def merge_carts(cls, guest_cart, user_cart):
        if not guest_cart or not user_cart or guest_cart.pk == user_cart.pk:
            return user_cart

        guest_cart = Cart.objects.select_for_update().get(pk=guest_cart.pk)
        user_cart = Cart.objects.select_for_update().get(pk=user_cart.pk)

        if guest_cart.status != Cart.Status.ACTIVE:
            return user_cart

        guest_items = (
            CartItem.objects.select_for_update()
            .select_related('product_variant')
            .filter(cart=guest_cart)
        )

        for guest_item in guest_items:
            product_variant = type(
                guest_item.product_variant,
            ).objects.select_for_update().get(pk=guest_item.product_variant_id)
            user_item = (
                CartItem.objects.select_for_update()
                .filter(cart=user_cart, product_variant=product_variant)
                .first()
            )
            merged_quantity = cls._resolve_merge_quantity(
                existing_quantity=user_item.quantity if user_item else 0,
                incoming_quantity=guest_item.quantity,
                stock_quantity=product_variant.stock_quantity,
            )

            if merged_quantity < 1:
                if user_item:
                    user_item.delete()
                continue

            if user_item:
                user_item.quantity = merged_quantity
                user_item.save(update_fields=['quantity', 'updated_at'])
                continue

            CartItem.objects.create(
                cart=user_cart,
                product_variant=product_variant,
                quantity=merged_quantity,
                unit_price=guest_item.unit_price,
                tenant=user_cart.tenant,
            )

        guest_cart.status = Cart.Status.MERGED
        guest_cart.save(update_fields=['status', 'updated_at'])
        cls._invalidate_cart_after_commit(guest_cart)
        cls._invalidate_cart_after_commit(user_cart)
        return user_cart

    @staticmethod
    def _resolve_merge_quantity(
        existing_quantity,
        incoming_quantity,
        stock_quantity,
    ):
        requested_quantity = existing_quantity + incoming_quantity
        return max(min(requested_quantity, stock_quantity), 0)

    @classmethod
    def _store_cart_after_commit(cls, cart):
        if not cart.session_key:
            return

        transaction.on_commit(lambda: cls._store_cart(cart.pk))

    @classmethod
    def _invalidate_cart_after_commit(cls, cart):
        if not cart.session_key:
            return

        transaction.on_commit(lambda: cls._invalidate_cart(cart.session_key))

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
    def _invalidate_cart(session_key):
        try:
            CartRedisCache.invalidate_cart(session_key)
        except RedisError:
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
