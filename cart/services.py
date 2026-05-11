from django.db import transaction

from tenants.middleware import get_current_tenant

from .models import Cart, CartItem


class CartService:
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
            return item

        return CartItem.objects.create(
            cart=cart,
            product_variant=product_variant,
            quantity=quantity,
            unit_price=product_variant.variant_price,
            tenant=cart.tenant,
        )

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
        return item
