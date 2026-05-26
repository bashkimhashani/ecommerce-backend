from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsCustomer, IsVendorAdmin

from .serializers import OrderSerializer
from .services import (
    InvalidOrderFilterError,
    InvalidOrderTransitionError,
    OrderNotFoundError,
    OrderService,
)


class CustomerOrderListView(APIView):
    permission_classes = [IsCustomer]

    @extend_schema(
        tags=["Orders"],
        responses={status.HTTP_200_OK: OrderSerializer(many=True)},
        examples=[
            OpenApiExample(
                "Customer orders response",
                value=[
                    {
                        "id": 1,
                        "order_number": "ORD-20260524-0001",
                        "status": "confirmed",
                        "shipping_address": {
                            "full_name": "Customer User",
                            "line1": "Main street 1",
                            "city": "Prishtina",
                            "postal_code": "10000",
                            "country": "Kosovo",
                        },
                        "subtotal": "1299.00",
                        "total_amount": "1299.00",
                    },
                ],
                response_only=True,
            ),
        ],
    )
    def get(self, request):
        orders = OrderService.list_customer_orders(request.user)
        return Response(OrderSerializer(orders, many=True).data)


class CustomerOrderDetailView(APIView):
    permission_classes = [IsCustomer]

    @extend_schema(
        tags=["Orders"],
        responses={
            status.HTTP_200_OK: OrderSerializer,
            status.HTTP_404_NOT_FOUND: OpenApiResponse(
                description="Order not found.",
            ),
        },
        examples=[
            OpenApiExample(
                "Customer order detail response",
                value={
                    "id": 1,
                    "order_number": "ORD-20260524-0001",
                    "status": "confirmed",
                    "shipping_address": {
                        "full_name": "Customer User",
                        "line1": "Main street 1",
                        "city": "Prishtina",
                        "postal_code": "10000",
                        "country": "Kosovo",
                    },
                    "subtotal": "1299.00",
                    "total_amount": "1299.00",
                },
                response_only=True,
            ),
        ],
    )
    def get(self, request, order_number):
        order = OrderService.get_customer_order(request.user, order_number)
        if order is None:
            return Response(
                {"detail": "Order not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(OrderSerializer(order).data)


class CustomerOrderCancelView(APIView):
    permission_classes = [IsCustomer]

    @extend_schema(
        tags=["Orders"],
        request=None,
        responses={
            status.HTTP_200_OK: OrderSerializer,
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description="Order cannot be cancelled from current status.",
            ),
            status.HTTP_404_NOT_FOUND: OpenApiResponse(
                description="Order not found.",
            ),
        },
        examples=[
            OpenApiExample(
                "Cancelled order response",
                value={
                    "id": 1,
                    "order_number": "ORD-20260524-0001",
                    "status": "cancelled",
                    "subtotal": "1299.00",
                    "total_amount": "1299.00",
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request, order_id):
        try:
            order = OrderService.cancel_customer_order(request.user, order_id)
        except OrderNotFoundError:
            return Response(
                {"detail": "Order not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except InvalidOrderTransitionError as exc:
            return Response(
                {"detail": exc.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(OrderSerializer(order).data)


class VendorOrderListView(APIView):
    permission_classes = [IsVendorAdmin]

    @extend_schema(
        tags=["Vendor Orders"],
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                required=False,
                description="Filter by order status.",
            ),
            OpenApiParameter(
                name="date_from",
                type=str,
                required=False,
                description="Filter orders created on or after YYYY-MM-DD.",
            ),
            OpenApiParameter(
                name="date_to",
                type=str,
                required=False,
                description="Filter orders created on or before YYYY-MM-DD.",
            ),
        ],
        responses={
            status.HTTP_200_OK: OrderSerializer(many=True),
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description="Invalid status or date filter.",
            ),
        },
        examples=[
            OpenApiExample(
                "Vendor orders response",
                value=[
                    {
                        "id": 1,
                        "order_number": "ORD-20260524-0001",
                        "status": "processing",
                        "subtotal": "1299.00",
                        "total_amount": "1299.00",
                    },
                ],
                response_only=True,
            ),
        ],
    )
    def get(self, request):
        try:
            orders = OrderService.list_vendor_orders(
                request.user,
                request.query_params,
            )
        except InvalidOrderFilterError as exc:
            return Response(
                {"detail": exc.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(OrderSerializer(orders, many=True).data)


class VendorOrderTransitionView(APIView):
    permission_classes = [IsVendorAdmin]
    transition_method = None
    invalid_transition_message = "Order cannot be updated from its current status."

    @extend_schema(
        tags=["Vendor Orders"],
        request=None,
        responses={
            status.HTTP_200_OK: OrderSerializer,
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description="Invalid order status transition.",
            ),
            status.HTTP_404_NOT_FOUND: OpenApiResponse(
                description="Order not found.",
            ),
        },
        examples=[
            OpenApiExample(
                "Order transition response",
                value={
                    "id": 1,
                    "order_number": "ORD-20260524-0001",
                    "status": "processing",
                    "subtotal": "1299.00",
                    "total_amount": "1299.00",
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request, order_id):
        try:
            order = OrderService.transition_vendor_order(
                request.user,
                order_id,
                self.transition_method,
                self.invalid_transition_message,
            )
        except OrderNotFoundError:
            return Response(
                {"detail": "Order not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except InvalidOrderTransitionError as exc:
            return Response(
                {"detail": exc.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(OrderSerializer(order).data)


class VendorOrderConfirmView(VendorOrderTransitionView):
    transition_method = "confirm"
    invalid_transition_message = "Order cannot be confirmed from its current status."


class VendorOrderMarkShippedView(VendorOrderTransitionView):
    transition_method = "mark_shipped"
    invalid_transition_message = (
        "Order cannot be marked shipped from its current status."
    )


class VendorOrderMarkDeliveredView(VendorOrderTransitionView):
    transition_method = "mark_delivered"
    invalid_transition_message = (
        "Order cannot be marked delivered from its current status."
    )
