from django.db import transaction
from django_fsm import TransitionNotAllowed
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsVendorAdmin

from .models import Order
from .serializers import OrderSerializer


class VendorOrderConfirmView(APIView):
    permission_classes = [IsVendorAdmin]

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
            order.confirm()
        except TransitionNotAllowed:
            return Response(
                {'detail': 'Order cannot be confirmed from its current status.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.save(update_fields=['status', 'updated_at'])
        return Response(OrderSerializer(order).data)
