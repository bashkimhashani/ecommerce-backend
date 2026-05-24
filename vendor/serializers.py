from rest_framework import serializers

from .models import VendorProfile


class VendorAnalyticsAskSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=1000, trim_whitespace=True)


class VendorAnalyticsResponseSerializer(serializers.Serializer):
    answer = serializers.CharField()
    query = serializers.DictField()
    result = serializers.DictField()


class VendorProfileSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = VendorProfile
        fields = [
            'id', 'user', 'user_email', 'user_name', 'tenant',
            'store_name', 'store_description', 'logo', 'contact_email',
            'contact_phone', 'is_active', 'rating', 'total_sales',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'rating', 'total_sales']

class OrderSummarySerializer(serializers.Serializer):
    """Serializer for vendor order summary"""
    status = serializers.CharField()
    count = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
