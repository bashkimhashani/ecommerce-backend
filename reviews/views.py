from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order, OrderItem
from users.permissions import IsCustomer, IsVendorAdmin

from .models import ProductReview
from .serializers import (
    ProductReviewCreateSerializer,
    ProductReviewSerializer,
    PurchasedItemSerializer,
)


class PurchasedItemsView(APIView):
    permission_classes = [IsCustomer]

    @extend_schema(
        tags=["Reviews"],
        responses={status.HTTP_200_OK: PurchasedItemSerializer(many=True)},
    )
    def get(self, request):
        allowed_statuses = [
            Order.Status.CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.DELIVERED,
        ]
        items = (
            OrderItem.all_objects.select_related(
                "order",
                "product_variant__product",
                "product_variant__product__vendor",
            )
            .prefetch_related("product_variant__product__images")
            .filter(order__user=request.user, order__status__in=allowed_statuses)
            .order_by("-order__created_at", "-id")
        )
        return Response(
            PurchasedItemSerializer(
                items,
                many=True,
                context={"request": request},
            ).data
        )


class CustomerReviewView(APIView):
    permission_classes = [IsCustomer]

    @extend_schema(
        tags=["Reviews"],
        request=ProductReviewCreateSerializer,
        responses={status.HTTP_201_CREATED: ProductReviewSerializer},
    )
    def post(self, request):
        serializer = ProductReviewCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        review = serializer.save()
        return Response(
            ProductReviewSerializer(review).data,
            status=status.HTTP_201_CREATED,
        )


class VendorReviewListView(APIView):
    permission_classes = [IsVendorAdmin]

    @extend_schema(
        tags=["Vendor Reviews"],
        responses={status.HTTP_200_OK: ProductReviewSerializer(many=True)},
    )
    def get(self, request):
        vendor_profile = getattr(request.user, "vendor_profile", None)
        if vendor_profile is None:
            return Response([])

        reviews = ProductReview.all_objects.select_related(
            "user",
            "product",
            "vendor",
        ).filter(vendor=vendor_profile)
        return Response(ProductReviewSerializer(reviews, many=True).data)
