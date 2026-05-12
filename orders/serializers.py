from rest_framework import serializers

from .models import Order


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = [
            'id',
            'order_number',
            'status',
            'shipping_address',
            'subtotal',
            'total_amount',
            'created_at',
            'updated_at',
        ]
