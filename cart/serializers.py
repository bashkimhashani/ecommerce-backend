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
            'id',
            'product_variant_id',
            'product_name',
            'variant_label',
            'quantity',
            'unit_price',
            'line_total',
        ]

    def get_product_name(self, obj):
        product = getattr(obj.product_variant, 'product', None)
        return getattr(product, 'name', '')

    def get_variant_label(self, obj):
        variant = obj.product_variant
        options = [
            getattr(variant, 'color', ''),
            getattr(variant, 'storage', ''),
            getattr(variant, 'ram', ''),
        ]
        return ', '.join(option for option in options if option)


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
            'id',
            'status',
            'items',
            'total_items',
            'subtotal',
            'created_at',
            'updated_at',
        ]
