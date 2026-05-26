from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsSuperAdmin

from .serializers import RequestLogSerializer
from .services import RequestLogService


class RequestLogPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class AdminRequestLogListView(APIView):
    permission_classes = [IsSuperAdmin]
    pagination_class = RequestLogPagination

    @extend_schema(
        tags=['Admin'],
        parameters=[
            OpenApiParameter(
                name='page',
                type=int,
                required=False,
                description='Page number to return.',
            ),
            OpenApiParameter(
                name='page_size',
                type=int,
                required=False,
                description='Number of request log rows per page.',
            ),
        ],
        responses={
            status.HTTP_200_OK: inline_serializer(
                name='PaginatedRequestLogResponse',
                fields={
                    'count': serializers.IntegerField(),
                    'next': serializers.URLField(allow_null=True),
                    'previous': serializers.URLField(allow_null=True),
                    'results': RequestLogSerializer(many=True),
                },
            ),
        },
        examples=[
            OpenApiExample(
                'Request logs response',
                value={
                    'count': 1,
                    'next': None,
                    'previous': None,
                    'results': [
                        {
                            'id': 1,
                            'method': 'GET',
                            'path': '/api/v1/catalog/products/',
                            'status_code': 200,
                            'response_time_ms': 24,
                            'tenant_id': 1,
                            'created_at': '2026-05-24T10:00:00Z',
                        },
                    ],
                },
                response_only=True,
            ),
        ],
    )
    def get(self, request):
        logs = RequestLogService.list_logs()
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(logs, request, view=self)
        serializer = RequestLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
