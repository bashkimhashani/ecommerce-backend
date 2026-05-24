from django.db import transaction
from django.utils.dateparse import parse_date
from django_fsm import TransitionNotAllowed
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

from .models import Order
from .serializers import OrderSerializer


class CustomerOrderListView(APIView):
    permission_classes = [IsCustomer]

    @extend_schema(
        tags=['Orders'],
        responses={status.HTTP_200_OK: OrderSerializer(many=True)},
        examples=[
            OpenApiExample(
                'Customer orders response',
                value=[
                    {
                        'id': 1,
                        'order_number': 'ORD-20260524-0001',
                        'status': 'confirmed',
                        'shipping_address': {
                            'full_name': 'Customer User',
                            'line1': 'Main street 1',
                            'city': 'Prishtina',
                            'postal_code': '10000',
                            'country': 'Kosovo',
                        },
                        'subtotal': '1299.00',
                        'total_amount': '1299.00',
                    },
                ],
                response_only=True,
            ),
        ],
    )
    def get(self, request):
        orders = Order.objects.filter(
            user=request.user,
            tenant=request.user.tenant,
        ).select_related(
            'checkout_session',
        )

        return Response(OrderSerializer(orders, many=True).data)


class CustomerOrderDetailView(APIView):
    permission_classes = [IsCustomer]

    @extend_schema(
        tags=['Orders'],
        responses={
            status.HTTP_200_OK: OrderSerializer,
            status.HTTP_404_NOT_FOUND: OpenApiResponse(
                description='Order not found.',
            ),
        },
        examples=[
            OpenApiExample(
                'Customer order detail response',
                value={
                    'id': 1,
                    'order_number': 'ORD-20260524-0001',
                    'status': 'confirmed',
                    'shipping_address': {
                        'full_name': 'Customer User',
                        'line1': 'Main street 1',
                        'city': 'Prishtina',
                        'postal_code': '10000',
                        'country': 'Kosovo',
                    },
                    'subtotal': '1299.00',
                    'total_amount': '1299.00',
                },
                response_only=True,
            ),
        ],
    )
    def get(self, request, order_number):
        order = Order.objects.filter(
            order_number=order_number,
            user=request.user,
            tenant=request.user.tenant,
        ).select_related(
            'checkout_session',
        ).first()
        if order is None:
            return Response(
                {'detail': 'Order not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(OrderSerializer(order).data)


class CustomerOrderCancelView(APIView):
    permission_classes = [IsCustomer]

    @extend_schema(
        tags=['Orders'],
        request=None,
        responses={
            status.HTTP_200_OK: OrderSerializer,
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description='Order cannot be cancelled from current status.',
            ),
            status.HTTP_404_NOT_FOUND: OpenApiResponse(
                description='Order not found.',
            ),
        },
        examples=[
            OpenApiExample(
                'Cancelled order response',
                value={
                    'id': 1,
                    'order_number': 'ORD-20260524-0001',
                    'status': 'cancelled',
                    'subtotal': '1299.00',
                    'total_amount': '1299.00',
                },
                response_only=True,
            ),
        ],
    )
    @transaction.atomic
    def post(self, request, order_id):
        order = Order.objects.select_for_update().filter(
            pk=order_id,
            user=request.user,
            tenant=request.user.tenant,
        ).first()
        if order is None:
            return Response(
                {'detail': 'Order not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            order.cancel()
        except TransitionNotAllowed:
            return Response(
                {
                    'detail': (
                        'Order cannot be cancelled from its current status.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.save(update_fields=['status', 'updated_at'])
        return Response(OrderSerializer(order).data)


class VendorOrderListView(APIView):
    permission_classes = [IsVendorAdmin]

    @extend_schema(
        tags=['Vendor Orders'],
        parameters=[
            OpenApiParameter(
                name='status',
                type=str,
                required=False,
                description='Filter by order status.',
            ),
            OpenApiParameter(
                name='date_from',
                type=str,
                required=False,
                description='Filter orders created on or after YYYY-MM-DD.',
            ),
            OpenApiParameter(
                name='date_to',
                type=str,
                required=False,
                description='Filter orders created on or before YYYY-MM-DD.',
            ),
        ],
        responses={
            status.HTTP_200_OK: OrderSerializer(many=True),
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description='Invalid status or date filter.',
            ),
        },
        examples=[
            OpenApiExample(
                'Vendor orders response',
                value=[
                    {
                        'id': 1,
                        'order_number': 'ORD-20260524-0001',
                        'status': 'processing',
                        'subtotal': '1299.00',
                        'total_amount': '1299.00',
                    },
                ],
                response_only=True,
            ),
        ],
    )
    def get(self, request):
        orders = Order.objects.filter(
            tenant=request.user.tenant,
        ).select_related(
            'user',
            'checkout_session',
        )

        status_filter = request.query_params.get('status')
        if status_filter:
            valid_statuses = {choice[0] for choice in Order.Status.choices}
            if status_filter not in valid_statuses:
                return Response(
                    {'detail': 'Invalid order status filter.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            orders = orders.filter(status=status_filter)

        date_from = request.query_params.get('date_from')
        if date_from:
            parsed_date_from = parse_date(date_from)
            if parsed_date_from is None:
                return Response(
                    {'detail': 'Invalid date_from filter.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            orders = orders.filter(created_at__date__gte=parsed_date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            parsed_date_to = parse_date(date_to)
            if parsed_date_to is None:
                return Response(
                    {'detail': 'Invalid date_to filter.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            orders = orders.filter(created_at__date__lte=parsed_date_to)

        return Response(OrderSerializer(orders, many=True).data)


class VendorOrderTransitionView(APIView):
    permission_classes = [IsVendorAdmin]
    transition_method = None
    invalid_transition_message = 'Order cannot be updated from its current status.'

    @extend_schema(
        tags=['Vendor Orders'],
        request=None,
        responses={
            status.HTTP_200_OK: OrderSerializer,
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description='Invalid order status transition.',
            ),
            status.HTTP_404_NOT_FOUND: OpenApiResponse(
                description='Order not found.',
            ),
        },
        examples=[
            OpenApiExample(
                'Order transition response',
                value={
                    'id': 1,
                    'order_number': 'ORD-20260524-0001',
                    'status': 'processing',
                    'subtotal': '1299.00',
                    'total_amount': '1299.00',
                },
                response_only=True,
            ),
        ],
    )
    @transaction.atomic
    def post(self, request, order_id):
        order = Order.objects.select_for_update().filter(
            pk=order_id,
            tenant=request.user.tenant,
        ).first()
        if order is None:
            return Response(
                {'detail': 'Order not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            getattr(order, self.transition_method)()
        except TransitionNotAllowed:
            return Response(
                {'detail': self.invalid_transition_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.save(update_fields=['status', 'updated_at'])
        return Response(OrderSerializer(order).data)


class VendorOrderConfirmView(VendorOrderTransitionView):
    transition_method = 'confirm'
    invalid_transition_message = (
        'Order cannot be confirmed from its current status.'
    )


class VendorOrderMarkShippedView(VendorOrderTransitionView):
    transition_method = 'mark_shipped'
    invalid_transition_message = (
        'Order cannot be marked shipped from its current status.'
    )


class VendorOrderMarkDeliveredView(VendorOrderTransitionView):
    transition_method = 'mark_delivered'
    invalid_transition_message = (
        'Order cannot be marked delivered from its current status.'
    )
