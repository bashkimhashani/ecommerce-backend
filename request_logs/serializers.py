from rest_framework import serializers

from .models import RequestLog


class RequestLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequestLog
        fields = [
            'id',
            'method',
            'path',
            'status_code',
            'response_time_ms',
            'tenant_id',
            'created_at',
        ]
