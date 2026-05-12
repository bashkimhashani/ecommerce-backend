from django.db import transaction

from cart.models import Cart, CartItem
from orders.models import Order, OrderItem

from .models import CheckoutSession


class InsufficientStockError(ValueError):
    pass


class OrderCreationService:
    @classmethod
    @transaction.atomic
    def create_from_checkout(cls, checkout_session):
        checkout_session = (
            CheckoutSession.objects.select_for_update()
            .select_related('cart', 'user')
            .get(pk=checkout_session.pk)
        )

        existing_order = Order.objects.filter(
            checkout_session=checkout_session,
        ).first()
        if existing_order:
            return existing_order

        cart = Cart.objects.select_for_update().get(
            pk=checkout_session.cart_id,
        )
        cart_items = list(
            CartItem.objects.select_for_update()
            .select_related('product_variant__product')
            .filter(cart=cart)
        )

        if not cart_items:
            raise ValueError('Cannot create an order from an empty cart.')

        order = Order.objects.create(
            user=checkout_session.user,
            checkout_session=checkout_session,
            shipping_address=checkout_session.shipping_address,
            subtotal=cart.subtotal,
            total_amount=cart.subtotal,
            tenant=checkout_session.tenant,
        )

        for cart_item in cart_items:
            product_variant = cls._lock_product_variant(cart_item)

            if product_variant.stock_quantity < cart_item.quantity:
                raise InsufficientStockError(
                    'Requested quantity exceeds available stock.',
                )

            product_variant.stock_quantity -= cart_item.quantity
            product_variant.save(update_fields=['stock_quantity'])
            OrderItem.objects.create(
                order=order,
                product_variant=product_variant,
                product_name=cls._product_name(cart_item),
                variant_label=cls._variant_label(cart_item),
                quantity=cart_item.quantity,
                unit_price=cart_item.unit_price,
                line_total=cart_item.line_total,
                tenant=order.tenant,
            )

        checkout_session.status = CheckoutSession.Status.COMPLETED
        checkout_session.save(update_fields=['status', 'updated_at'])

        cart.status = Cart.Status.CHECKED_OUT
        cart.save(update_fields=['status', 'updated_at'])
        cart.items.all().delete()
        return order

    @staticmethod
    def _lock_product_variant(cart_item):
        return type(
            cart_item.product_variant,
        ).objects.select_for_update().get(pk=cart_item.product_variant_id)

    @staticmethod
    def _product_name(cart_item):
        product = getattr(cart_item.product_variant, 'product', None)
        return getattr(product, 'name', '')

    @staticmethod
    def _variant_label(cart_item):
        product_variant = cart_item.product_variant
        variant_options = [
            getattr(product_variant, 'color', ''),
            getattr(product_variant, 'storage', ''),
            getattr(product_variant, 'ram', ''),
        ]
        return ', '.join(option for option in variant_options if option)
