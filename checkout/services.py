from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
import stripe

from cart.models import Cart, CartItem
from cart.services import CartService
from notifications.tasks import send_order_confirmation
from orders.models import Order, OrderItem

from .models import CheckoutSession


class InsufficientStockError(ValueError):
    pass


class StripeConfigurationError(ValueError):
    pass


class CheckoutSessionConflictError(ValueError):
    pass


class CheckoutSessionNotFoundError(ValueError):
    pass


class CheckoutSessionService:
    @classmethod
    @transaction.atomic
    def create_session(cls, request, data):
        cart = CartService.get_or_create_cart(request)
        if not cart.items.exists():
            raise ValueError(
                "Cannot create checkout session for an empty cart.",
            )

        checkout_session, created = CheckoutSession.objects.get_or_create(
            tenant=cart.tenant,
            idempotency_key=data["idempotency_key"],
            defaults={
                "user": request.user,
                "cart": cart,
                "shipping_address": data.get("shipping_address", {}),
            },
        )

        if checkout_session.user_id != request.user.id:
            raise CheckoutSessionConflictError(
                "Idempotency key is already in use.",
            )

        return checkout_session, created

    @staticmethod
    def update_shipping_address(user, session_id, shipping_address):
        checkout_session = CheckoutSession.objects.filter(
            pk=session_id,
            user=user,
        ).first()
        if checkout_session is None:
            raise CheckoutSessionNotFoundError("Checkout session not found.")

        checkout_session.shipping_address = shipping_address
        update_fields = ["shipping_address", "updated_at"]
        if checkout_session.status == CheckoutSession.Status.PENDING:
            checkout_session.status = CheckoutSession.Status.READY
            update_fields.append("status")

        checkout_session.save(update_fields=update_fields)
        return checkout_session

    @classmethod
    def create_payment_intent_response(cls, user, session_id):
        checkout_session = cls.get_ready_payment_session(user, session_id)
        payment_intent = PaymentIntentService.create_for_checkout(
            checkout_session,
        )
        return {
            "payment_intent_id": stripe_value(payment_intent, "id"),
            "client_secret": stripe_value(payment_intent, "client_secret"),
            "amount": stripe_value(payment_intent, "amount"),
            "currency": stripe_value(payment_intent, "currency"),
        }

    @staticmethod
    def get_ready_payment_session(user, session_id):
        checkout_session = (
            CheckoutSession.objects.select_related(
                "cart",
                "user",
            )
            .filter(
                pk=session_id,
                user=user,
            )
            .first()
        )
        if checkout_session is None:
            raise CheckoutSessionNotFoundError("Checkout session not found.")

        if checkout_session.status != CheckoutSession.Status.READY:
            raise ValueError("Checkout session must be ready for payment.")

        if not checkout_session.shipping_address:
            raise ValueError("Shipping address is required before payment.")

        if not checkout_session.cart.items.exists():
            raise ValueError(
                "Cannot create payment intent for an empty cart.",
            )

        return checkout_session

    @staticmethod
    def handle_webhook(payload, signature):
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        if not webhook_secret:
            raise StripeConfigurationError(
                "Stripe webhook secret is not configured.",
            )

        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=webhook_secret,
        )
        order = StripeWebhookService.handle_event(event)
        response_data = {"received": True}
        if order is not None:
            response_data["order_number"] = order.order_number
            response_data["order_status"] = order.status
        return response_data


class PaymentIntentService:
    @classmethod
    def create_for_checkout(cls, checkout_session):
        if not settings.STRIPE_SECRET_KEY:
            raise StripeConfigurationError("Stripe secret key is not configured.")

        cart = checkout_session.cart
        amount = cls._amount_to_cents(cart.subtotal)
        if amount < 1:
            raise ValueError("Payment amount must be greater than zero.")

        return stripe.PaymentIntent.create(
            amount=amount,
            currency="usd",
            automatic_payment_methods={
                "enabled": True,
            },
            metadata={
                "checkout_session_id": str(checkout_session.id),
                "cart_id": str(cart.id),
                "user_id": str(checkout_session.user_id),
                "tenant_id": str(checkout_session.tenant_id),
            },
            idempotency_key=f"checkout-session-{checkout_session.id}",
        )

    @staticmethod
    def _amount_to_cents(amount):
        cents = Decimal(amount) * Decimal("100")
        return int(cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class StripeWebhookService:
    @classmethod
    def handle_event(cls, event):
        event_type = stripe_value(event, "type")
        if event_type != "payment_intent.succeeded":
            return None

        payment_intent = stripe_value(stripe_value(event, "data"), "object")
        return cls.handle_payment_intent_succeeded(payment_intent)

    @classmethod
    def handle_payment_intent_succeeded(cls, payment_intent):
        metadata = stripe_value(payment_intent, "metadata") or {}
        checkout_session_id = stripe_value(metadata, "checkout_session_id")
        if not checkout_session_id:
            raise ValueError(
                "Missing checkout_session_id in payment metadata.",
            )

        try:
            checkout_session = CheckoutSession.objects.get(
                pk=checkout_session_id,
            )
        except CheckoutSession.DoesNotExist as exc:
            raise ObjectDoesNotExist("Checkout session not found.") from exc
        order = OrderCreationService.create_from_checkout(checkout_session)
        if order.status == Order.Status.PENDING:
            order.confirm()
            order.save(update_fields=["status", "updated_at"])

        return order


class OrderCreationService:
    @classmethod
    @transaction.atomic
    def create_from_checkout(cls, checkout_session):
        checkout_session = (
            CheckoutSession.objects.select_for_update()
            .select_related("cart", "user")
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
            .select_related("product_variant__product")
            .filter(cart=cart)
        )

        if not cart_items:
            raise ValueError("Cannot create an order from an empty cart.")

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
            cls._decrement_stock(product_variant, cart_item.quantity)
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
        checkout_session.save(update_fields=["status", "updated_at"])

        cls._clear_cart(cart)
        transaction.on_commit(
            lambda: send_order_confirmation.delay(order.pk),
        )
        return order

    @staticmethod
    def _clear_cart(cart):
        cart.status = Cart.Status.CHECKED_OUT
        cart.save(update_fields=["status", "updated_at"])
        cart.items.all().delete()

    @staticmethod
    def _lock_product_variant(cart_item):
        return (
            type(
                cart_item.product_variant,
            )
            .objects.select_for_update()
            .get(pk=cart_item.product_variant_id)
        )

    @staticmethod
    def _decrement_stock(product_variant, quantity):
        next_stock_quantity = product_variant.stock_quantity - quantity
        if next_stock_quantity < 0:
            raise InsufficientStockError(
                "Requested quantity exceeds available stock.",
            )

        product_variant.stock_quantity = next_stock_quantity
        product_variant.save(update_fields=["stock_quantity"])

    @staticmethod
    def _product_name(cart_item):
        product = getattr(cart_item.product_variant, "product", None)
        return getattr(product, "name", "")

    @staticmethod
    def _variant_label(cart_item):
        product_variant = cart_item.product_variant
        variant_options = [
            getattr(product_variant, "color", ""),
            getattr(product_variant, "storage", ""),
            getattr(product_variant, "ram", ""),
        ]
        return ", ".join(option for option in variant_options if option)


def stripe_value(value, key):
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
