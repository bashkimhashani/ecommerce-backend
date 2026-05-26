from rest_framework import serializers

from .models import CheckoutSession


class AddressSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=30)
    line1 = serializers.CharField(max_length=255)
    line2 = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
    )
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
    )
    postal_code = serializers.CharField(max_length=30)
    country = serializers.CharField(max_length=100)


class CheckoutSessionCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=False,
    )
    shipping_address = serializers.JSONField(required=False, default=dict)

    def validate_shipping_address(self, value):
        if not value:
            return {}

        serializer = AddressSerializer(data=value)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def validate(self, attrs):
        idempotency_key = attrs.get("idempotency_key") or self.context.get(
            "idempotency_key",
        )
        if not idempotency_key:
            raise serializers.ValidationError(
                {
                    "idempotency_key": "This field is required.",
                }
            )

        attrs["idempotency_key"] = idempotency_key
        return attrs


class CheckoutSessionSerializer(serializers.ModelSerializer):
    cart_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = CheckoutSession
        fields = [
            "id",
            "cart_id",
            "idempotency_key",
            "shipping_address",
            "status",
            "created_at",
            "updated_at",
        ]
