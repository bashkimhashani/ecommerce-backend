from django.db import transaction
from django_fsm import TransitionNotAllowed
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsVendorAdmin

from .models import Order
from .serializers import OrderSerializer


class VendorOrderTransitionView(APIView):
    permission_classes = [IsVendorAdmin]
    transition_method = None
    invalid_transition_message = 'Order cannot be updated from its current status.'

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
