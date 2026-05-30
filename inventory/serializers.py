from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from .models import Inventory


class InventorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source="product_variant.product.name",
        read_only=True,
    )
    product_sku = serializers.CharField(
        source="product_variant.product.sku",
        read_only=True,
    )
    product_slug = serializers.CharField(
        source="product_variant.product.slug",
        read_only=True,
    )
    variant_name = serializers.SerializerMethodField()
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Inventory
        fields = [
            "id",
            "product_variant",
            "product_name",
            "product_sku",
            "product_slug",
            "variant_name",
            "vendor",
            "tenant",
            "quantity",
            "low_stock_threshold",
            "is_low_stock",
            "created_at",
            "last_updated",
        ]
        read_only_fields = [
            "id",
            "product_variant",
            "product_name",
            "product_sku",
            "product_slug",
            "variant_name",
            "vendor",
            "tenant",
            "is_low_stock",
            "created_at",
            "last_updated",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_variant_name(self, obj):
        values = [
            obj.product_variant.color,
            obj.product_variant.storage,
            obj.product_variant.ram,
        ]
        return " / ".join(value for value in values if value) or "Default"
