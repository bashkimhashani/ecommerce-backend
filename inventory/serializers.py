from rest_framework import serializers
from .models import Inventory

class InventorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    available_quantity = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Inventory
        fields = [
            'id', 'product', 'product_name', 'vendor', 'tenant',
            'quantity_available', 'reserved_quantity', 'available_quantity',
            'low_stock_threshold', 'price', 'compare_at_price', 'cost_per_item',
            'is_active', 'is_tracked', 'sku', 'barcode', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']