from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from cart.services import CartService
from users.permissions import IsCustomer

from .models import CheckoutSession
from .serializers import (
    AddressSerializer,
    CheckoutSessionCreateSerializer,
    CheckoutSessionSerializer,
)


class CheckoutSessionCreateView(APIView):
    permission_classes = [IsCustomer]

    @transaction.atomic
    def post(self, request):
        serializer = CheckoutSessionCreateSerializer(
            data=request.data,
            context={
                'idempotency_key': request.headers.get('Idempotency-Key'),
            },
        )
        serializer.is_valid(raise_exception=True)

        cart = CartService.get_or_create_cart(request)
        if not cart.items.exists():
            return Response(
                {'detail': 'Cannot create checkout session for an empty cart.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        checkout_session, created = CheckoutSession.objects.get_or_create(
            tenant=cart.tenant,
            idempotency_key=serializer.validated_data['idempotency_key'],
            defaults={
                'user': request.user,
                'cart': cart,
                'shipping_address': serializer.validated_data.get(
                    'shipping_address',
                    {},
                ),
            },
        )

        if checkout_session.user_id != request.user.id:
            return Response(
                {'detail': 'Idempotency key is already in use.'},
                status=status.HTTP_409_CONFLICT,
            )

        response_status = (
            status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
        return Response(
            CheckoutSessionSerializer(checkout_session).data,
            status=response_status,
        )


class CheckoutSessionAddressUpdateView(APIView):
    permission_classes = [IsCustomer]

    def patch(self, request, session_id):
        checkout_session = CheckoutSession.objects.filter(
            pk=session_id,
            user=request.user,
        ).first()
        if checkout_session is None:
            return Response(
                {'detail': 'Checkout session not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        checkout_session.shipping_address = serializer.validated_data
        update_fields = ['shipping_address', 'updated_at']
        if checkout_session.status == CheckoutSession.Status.PENDING:
            checkout_session.status = CheckoutSession.Status.READY
            update_fields.append('status')

        checkout_session.save(update_fields=update_fields)
        return Response(CheckoutSessionSerializer(checkout_session).data)
