from django.db import transaction
from django.utils.dateparse import parse_date
from django_fsm import TransitionNotAllowed

from .models import Order


class OrderServiceError(Exception):
    default_detail = "Order service error."

    def __init__(self, detail=None):
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class OrderNotFoundError(OrderServiceError):
    default_detail = "Order not found."


class InvalidOrderFilterError(OrderServiceError):
    default_detail = "Invalid order filter."


class InvalidOrderTransitionError(OrderServiceError):
    default_detail = "Order cannot be updated from its current status."


class OrderService:
    @staticmethod
    def list_customer_orders(user):
        return Order.objects.filter(
            user=user,
            tenant=user.tenant,
        ).select_related(
            "checkout_session",
        )

    @staticmethod
    def get_customer_order(user, order_number):
        return (
            Order.objects.filter(
                order_number=order_number,
                user=user,
                tenant=user.tenant,
            )
            .select_related(
                "checkout_session",
            )
            .first()
        )

    @staticmethod
    @transaction.atomic
    def cancel_customer_order(user, order_id):
        order = (
            Order.objects.select_for_update()
            .filter(
                pk=order_id,
                user=user,
                tenant=user.tenant,
            )
            .first()
        )
        if order is None:
            raise OrderNotFoundError()

        try:
            order.cancel()
        except TransitionNotAllowed as exc:
            raise InvalidOrderTransitionError(
                "Order cannot be cancelled from its current status.",
            ) from exc

        order.save(update_fields=["status", "updated_at"])
        return order

    @staticmethod
    def list_vendor_orders(user, filters):
        orders = Order.objects.filter(
            tenant=user.tenant,
        ).select_related(
            "user",
            "checkout_session",
        )

        status_filter = filters.get("status")
        if status_filter:
            valid_statuses = {choice[0] for choice in Order.Status.choices}
            if status_filter not in valid_statuses:
                raise InvalidOrderFilterError("Invalid order status filter.")
            orders = orders.filter(status=status_filter)

        date_from = filters.get("date_from")
        if date_from:
            parsed_date_from = parse_date(date_from)
            if parsed_date_from is None:
                raise InvalidOrderFilterError("Invalid date_from filter.")
            orders = orders.filter(created_at__date__gte=parsed_date_from)

        date_to = filters.get("date_to")
        if date_to:
            parsed_date_to = parse_date(date_to)
            if parsed_date_to is None:
                raise InvalidOrderFilterError("Invalid date_to filter.")
            orders = orders.filter(created_at__date__lte=parsed_date_to)

        return orders

    @staticmethod
    @transaction.atomic
    def transition_vendor_order(user, order_id, transition_method, error_message):
        order = (
            Order.objects.select_for_update()
            .filter(
                pk=order_id,
                tenant=user.tenant,
            )
            .first()
        )
        if order is None:
            raise OrderNotFoundError()

        try:
            getattr(order, transition_method)()
        except TransitionNotAllowed as exc:
            raise InvalidOrderTransitionError(error_message) from exc

        order.save(update_fields=["status", "updated_at"])
        return order
