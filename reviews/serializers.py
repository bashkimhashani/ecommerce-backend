from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from orders.models import Order, OrderItem

from .models import ProductReview


class ProductReviewSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    vendor_name = serializers.CharField(source="vendor.store_name", read_only=True)

    class Meta:
        model = ProductReview
        fields = [
            "id",
            "rating",
            "title",
            "comment",
            "customer_name",
            "product_name",
            "product_slug",
            "vendor_name",
            "created_at",
            "updated_at",
        ]

    def get_customer_name(self, obj):
        full_name = obj.user.get_full_name()
        return full_name or obj.user.email


class PurchasedItemSerializer(serializers.ModelSerializer):
    order_item_id = serializers.IntegerField(source="id")
    order_number = serializers.CharField(source="order.order_number")
    order_status = serializers.CharField(source="order.status")
    product_id = serializers.IntegerField(source="product_variant.product.id")
    product_name = serializers.CharField(source="product_variant.product.name")
    product_slug = serializers.CharField(source="product_variant.product.slug")
    product_thumbnail = serializers.SerializerMethodField()
    vendor_name = serializers.CharField(
        source="product_variant.product.vendor.store_name",
        default="",
    )
    purchased_at = serializers.DateTimeField(source="order.created_at")
    existing_review = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "order_item_id",
            "order_number",
            "order_status",
            "product_id",
            "product_name",
            "product_slug",
            "product_thumbnail",
            "vendor_name",
            "variant_label",
            "quantity",
            "line_total",
            "purchased_at",
            "existing_review",
        ]

    def get_product_thumbnail(self, obj):
        image = obj.product_variant.product.images.order_by("sort_order", "id").first()
        if not image:
            return ""

        request = self.context.get("request")
        source = image.thumbnail or image.medium or image.image
        if not source:
            return ""

        url = source.url
        return request.build_absolute_uri(url) if request else url

    def get_existing_review(self, obj):
        try:
            review = obj.review
        except ObjectDoesNotExist:
            return None

        if review is None:
            return None
        return ProductReviewSerializer(review).data


class ProductReviewCreateSerializer(serializers.Serializer):
    order_item = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(max_length=120, allow_blank=True, required=False)
    comment = serializers.CharField()

    def validate_order_item(self, value):
        request = self.context["request"]
        allowed_statuses = [
            Order.Status.CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.DELIVERED,
        ]
        order_item = (
            OrderItem.all_objects.select_related(
                "order",
                "product_variant__product",
                "product_variant__product__vendor",
            )
            .filter(
                id=value,
                order__user=request.user,
                order__status__in=allowed_statuses,
            )
            .first()
        )

        if order_item is None:
            raise serializers.ValidationError(
                "You can only review products from completed purchases."
            )

        if order_item.product_variant.product.vendor is None:
            raise serializers.ValidationError("This product does not have a vendor.")

        return order_item

    def create(self, validated_data):
        order_item = validated_data["order_item"]
        product = order_item.product_variant.product
        review, _created = ProductReview.all_objects.update_or_create(
            order_item=order_item,
            defaults={
                "user": self.context["request"].user,
                "product": product,
                "vendor": product.vendor,
                "tenant": order_item.tenant or order_item.order.tenant,
                "rating": validated_data["rating"],
                "title": validated_data.get("title", "").strip(),
                "comment": validated_data["comment"].strip(),
            },
        )
        return review
