from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsSuperAdmin

from .models import RequestLog
from .serializers import RequestLogSerializer


class RequestLogPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class AdminRequestLogListView(APIView):
    permission_classes = [IsSuperAdmin]
    pagination_class = RequestLogPagination

    def get(self, request):
        logs = RequestLog.objects.all()
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(logs, request, view=self)
        serializer = RequestLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
