from rest_framework import serializers

from .models import CheckoutSession


class CheckoutSessionCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=False,
    )
    shipping_address = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        idempotency_key = attrs.get('idempotency_key') or self.context.get(
            'idempotency_key',
        )
        if not idempotency_key:
            raise serializers.ValidationError({
                'idempotency_key': 'This field is required.',
            })

        attrs['idempotency_key'] = idempotency_key
        return attrs


class CheckoutSessionSerializer(serializers.ModelSerializer):
    cart_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = CheckoutSession
        fields = [
            'id',
            'cart_id',
            'idempotency_key',
            'shipping_address',
            'status',
            'created_at',
            'updated_at',
        ]
