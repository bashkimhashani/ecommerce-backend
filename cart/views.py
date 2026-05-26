from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
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

    @extend_schema(
        tags=["Cart"],
        responses={status.HTTP_200_OK: CartSerializer},
        examples=[
            OpenApiExample(
                "Cart response",
                value={
                    "id": 1,
                    "status": "active",
                    "items": [
                        {
                            "id": 10,
                            "product_variant_id": 3,
                            "product_name": "TechBook Pro 14",
                            "variant_label": "Space Gray, 512GB, 16GB",
                            "quantity": 1,
                            "unit_price": "1299.00",
                            "line_total": "1299.00",
                        },
                    ],
                    "total_items": 1,
                    "subtotal": "1299.00",
                },
                response_only=True,
            ),
        ],
    )
    def get(self, request):
        return Response(CartService.get_serialized_cart(request))


class CartItemCreateView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Cart"],
        request=CartItemCreateSerializer,
        responses={
            status.HTTP_201_CREATED: CartItemSerializer,
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description="Invalid item payload or insufficient stock.",
            ),
        },
        examples=[
            OpenApiExample(
                "Add cart item request",
                value={"product_variant_id": 3, "quantity": 2},
                request_only=True,
            ),
            OpenApiExample(
                "Add cart item response",
                value={
                    "id": 10,
                    "product_variant_id": 3,
                    "product_name": "TechBook Pro 14",
                    "variant_label": "Space Gray, 512GB, 16GB",
                    "quantity": 2,
                    "unit_price": "1299.00",
                    "line_total": "2598.00",
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        cart = CartService.get_or_create_cart(request)
        serializer = CartItemCreateSerializer(
            data=request.data,
            context={"cart": cart},
        )
        serializer.is_valid(raise_exception=True)

        try:
            item = CartService.add_item(
                cart=cart,
                product_variant=serializer.validated_data["product_variant"],
                quantity=serializer.validated_data["quantity"],
            )
        except ValueError as exc:
            return Response(
                {"quantity": [str(exc)]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            CartItemSerializer(item).data,
            status=status.HTTP_201_CREATED,
        )


class CartItemDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Cart"],
        request=CartItemUpdateSerializer,
        responses={
            status.HTTP_200_OK: CartItemSerializer,
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description="Invalid quantity or insufficient stock.",
            ),
            status.HTTP_404_NOT_FOUND: OpenApiResponse(
                description="Cart item not found.",
            ),
        },
        examples=[
            OpenApiExample(
                "Update cart item request",
                value={"quantity": 3},
                request_only=True,
            ),
            OpenApiExample(
                "Update cart item response",
                value={
                    "id": 10,
                    "product_variant_id": 3,
                    "product_name": "TechBook Pro 14",
                    "variant_label": "Space Gray, 512GB, 16GB",
                    "quantity": 3,
                    "unit_price": "1299.00",
                    "line_total": "3897.00",
                },
                response_only=True,
            ),
        ],
    )
    def patch(self, request, item_id):
        cart = CartService.get_or_create_cart(request)
        serializer = CartItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            item = CartService.update_item_for_cart(
                cart=cart,
                item_id=item_id,
                quantity=serializer.validated_data["quantity"],
            )
        except ValueError as exc:
            return Response(
                {"quantity": [str(exc)]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if item is None:
            return Response(
                {"detail": "Cart item not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(CartItemSerializer(item).data)

    @extend_schema(
        tags=["Cart"],
        responses={
            status.HTTP_204_NO_CONTENT: OpenApiResponse(
                description="Cart item removed.",
            ),
            status.HTTP_404_NOT_FOUND: OpenApiResponse(
                description="Cart item not found.",
            ),
        },
    )
    def delete(self, request, item_id):
        cart = CartService.get_or_create_cart(request)
        if not CartService.remove_item_from_cart(cart, item_id):
            return Response(
                {"detail": "Cart item not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)
