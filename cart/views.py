from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    CartItemCreateSerializer,
    CartItemSerializer,
    CartItemUpdateSerializer,
    CartSerializer,
)
from .services import CartService


class CartDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(CartService.get_serialized_cart(request))


class CartItemCreateView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        cart = CartService.get_or_create_cart(request)
        serializer = CartItemCreateSerializer(
            data=request.data,
            context={'cart': cart},
        )
        serializer.is_valid(raise_exception=True)

        try:
            item = CartService.add_item(
                cart=cart,
                product_variant=serializer.validated_data['product_variant'],
                quantity=serializer.validated_data['quantity'],
            )
        except ValueError as exc:
            return Response(
                {'quantity': [str(exc)]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            CartItemSerializer(item).data,
            status=status.HTTP_201_CREATED,
        )


class CartItemDetailView(APIView):
    permission_classes = [AllowAny]

    def patch(self, request, item_id):
        cart = CartService.get_or_create_cart(request)
        item = cart.items.filter(pk=item_id).first()
        if item is None:
            return Response(
                {'detail': 'Cart item not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CartItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            item = CartService.update_item_quantity(
                item=item,
                quantity=serializer.validated_data['quantity'],
            )
        except ValueError as exc:
            return Response(
                {'quantity': [str(exc)]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(CartItemSerializer(item).data)

    def delete(self, request, item_id):
        cart = CartService.get_or_create_cart(request)
        item = cart.items.filter(pk=item_id).first()
        if item is None:
            return Response(
                {'detail': 'Cart item not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        CartService.remove_item(item)
        return Response(status=status.HTTP_204_NO_CONTENT)
