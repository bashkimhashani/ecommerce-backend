from rest_framework import serializers


class ChatMessageSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=4000, trim_whitespace=True)
    session_id = serializers.CharField(
        max_length=120,
        required=False,
        allow_blank=True,
    )


class ChatResponseSerializer(serializers.Serializer):
    session_id = serializers.CharField()
    message = serializers.CharField()
    used_fallback = serializers.BooleanField()
    products = serializers.ListField(child=serializers.DictField())
