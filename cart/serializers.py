from django.apps import apps
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product_variant_id = serializers.IntegerField(read_only=True)
    product_name = serializers.SerializerMethodField()
    variant_label = serializers.SerializerMethodField()
    line_total = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product_variant_id",
            "product_name",
            "variant_label",
            "quantity",
            "unit_price",
            "line_total",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_product_name(self, obj):
        product = getattr(obj.product_variant, "product", None)
        return getattr(product, "name", "")

    @extend_schema_field(OpenApiTypes.STR)
    def get_variant_label(self, obj):
        variant = obj.product_variant
        options = [
            getattr(variant, "color", ""),
            getattr(variant, "storage", ""),
            getattr(variant, "ram", ""),
        ]
        return ", ".join(option for option in options if option)


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    subtotal = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = Cart
        fields = [
            "id",
            "status",
            "items",
            "total_items",
            "subtotal",
            "created_at",
            "updated_at",
        ]


class CartItemCreateSerializer(serializers.Serializer):
    product_variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)

    def validate_product_variant_id(self, value):
        ProductVariant = apps.get_model("catalog", "ProductVariant")

        try:
            return ProductVariant.objects.get(pk=value)
        except ProductVariant.DoesNotExist:
            raise serializers.ValidationError("Product variant not found.")

    def validate(self, attrs):
        product_variant = attrs["product_variant_id"]
        quantity = attrs["quantity"]
        cart = self.context.get("cart")
        current_quantity = 0

        if cart:
            current_quantity = (
                CartItem.objects.filter(
                    cart=cart,
                    product_variant=product_variant,
                )
                .values_list("quantity", flat=True)
                .first()
                or 0
            )

        if current_quantity + quantity > product_variant.stock_quantity:
            raise serializers.ValidationError(
                {
                    "quantity": "Requested quantity exceeds available stock.",
                }
            )

        attrs["product_variant"] = product_variant
        del attrs["product_variant_id"]
        return attrs


class CartItemUpdateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
