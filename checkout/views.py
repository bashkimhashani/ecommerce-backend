from django.db import transaction
import stripe
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
from .services import PaymentIntentService, StripeConfigurationError


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


class CheckoutSessionPaymentIntentView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request, session_id):
        checkout_session = CheckoutSession.objects.select_related(
            'cart',
            'user',
        ).filter(
            pk=session_id,
            user=request.user,
        ).first()
        if checkout_session is None:
            return Response(
                {'detail': 'Checkout session not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if checkout_session.status != CheckoutSession.Status.READY:
            return Response(
                {'detail': 'Checkout session must be ready for payment.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not checkout_session.shipping_address:
            return Response(
                {'detail': 'Shipping address is required before payment.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not checkout_session.cart.items.exists():
            return Response(
                {'detail': 'Cannot create payment intent for an empty cart.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment_intent = PaymentIntentService.create_for_checkout(
                checkout_session,
            )
        except StripeConfigurationError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except ValueError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except stripe.StripeError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({
            'payment_intent_id': payment_intent_value(payment_intent, 'id'),
            'client_secret': payment_intent_value(
                payment_intent,
                'client_secret',
            ),
            'amount': payment_intent_value(payment_intent, 'amount'),
            'currency': payment_intent_value(payment_intent, 'currency'),
        })


def payment_intent_value(value, key):
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
