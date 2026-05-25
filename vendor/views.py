from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers, status
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)

from ai.services import AnalyticsQueryResolver, AnalyticsQueryValidationError
from inventory.serializers import InventorySerializer
from users.permissions import IsVendorAdmin
from .serializers import (
    AIReportSerializer,
    OrderSummarySerializer,
    VendorAnalyticsAskSerializer,
    VendorAnalyticsResponseSerializer,
)
from .services import VendorService
from .services import UnsupportedExportFormatError, VendorProfileNotFoundError


class VendorDashboardSummaryView(APIView):
    """
    GET /api/v1/vendor/dashboard/summary/
    Returns order count, revenue, and low stock alerts for the vendor.
    """
    permission_classes = [IsVendorAdmin]

    @extend_schema(
        tags=['Vendor Dashboard'],
        responses={
            200: OpenApiResponse(description='Vendor dashboard summary.'),
            404: OpenApiResponse(description='Vendor profile not found.'),
        },
    )
    def get(self, request):
        summary = VendorService.get_dashboard_summary(request.user)
        if summary is None:
            return Response(
                {'error': 'Vendor profile not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            'order_count': summary['order_count'],
            'revenue': summary['revenue'],
            'low_stock_alerts': summary['low_stock_alerts'],
            'low_stock_items': InventorySerializer(
                summary['low_stock_items'],
                many=True,
            ).data,
        })


class VendorLatestReportView(APIView):
    permission_classes = [IsVendorAdmin]

    @extend_schema(
        tags=['Vendor AI Insights'],
        responses={
            200: AIReportSerializer,
            204: OpenApiResponse(description='No report exists for tenant.'),
        },
    )
    def get(self, request):
        report = VendorService.get_latest_sales_report(request.user)
        if report is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        serializer = AIReportSerializer(report)
        return Response(serializer.data)


class VendorAnalyticsAskView(APIView):
    permission_classes = [IsVendorAdmin]

    @extend_schema(
        tags=['Vendor AI Insights'],
        request=VendorAnalyticsAskSerializer,
        responses={
            200: VendorAnalyticsResponseSerializer,
            400: OpenApiResponse(description='Unsupported analytics query.'),
        },
    )
    def post(self, request):
        serializer = VendorAnalyticsAskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = VendorService.resolve_analytics_query(
                user=request.user,
                question=serializer.validated_data['question'],
                resolver_class=AnalyticsQueryResolver,
            )
        except AnalyticsQueryValidationError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        response_serializer = VendorAnalyticsResponseSerializer(result)
        return Response(response_serializer.data)


class VendorInventoryListView(APIView):
    """
    GET /api/v1/vendor/inventory/
    Returns inventory rows for the authenticated vendor.
    """
    permission_classes = [IsVendorAdmin]

    @extend_schema(
        tags=['Vendor Inventory'],
        responses={
            200: InventorySerializer(many=True),
            404: OpenApiResponse(description='Vendor profile not found.'),
        },
    )
    def get(self, request):
        inventory = VendorService.list_inventory_for_user(request.user)
        if inventory is None:
            return Response(
                {'error': 'Vendor profile not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = InventorySerializer(inventory, many=True)
        return Response(serializer.data)


class VendorInventoryDetailView(APIView):
    """
    PATCH /api/v1/vendor/inventory/<id>/
    Updates an inventory row quantity or low stock threshold.
    """
    permission_classes = [IsVendorAdmin]

    @extend_schema(
        tags=['Vendor Inventory'],
        request=InventorySerializer,
        responses={
            200: InventorySerializer,
            400: OpenApiResponse(description='Invalid inventory payload.'),
            404: OpenApiResponse(description='Inventory row not found.'),
        },
    )
    def patch(self, request, pk):
        _, inventory = VendorService.get_inventory_item_for_user(
            request.user,
            pk,
        )
        if inventory is None:
            if VendorService.get_vendor_for_user(request.user) is None:
                return Response(
                    {'error': 'Vendor profile not found'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(
                {'error': 'Inventory item not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = InventorySerializer(
            inventory,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        VendorService.update_inventory_item(request.user, pk, serializer)
        return Response(serializer.data)


class VendorOrderSummaryView(APIView):
    """
    GET /api/v1/vendor/orders/summary/
    Returns order counts grouped by status for the authenticated vendor
    """
    permission_classes = [IsVendorAdmin]

    @extend_schema(
        tags=['Vendor Orders'],
        responses={
            200: OrderSummarySerializer(many=True),
            404: OpenApiResponse(description='Vendor profile not found.'),
        },
    )

    def get(self, request):
        vendor = VendorService.get_vendor_for_user(request.user)
        if vendor is None:
            return Response(
                {'error': 'Vendor profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        result = VendorService.get_order_summary(vendor)
        serializer = OrderSummarySerializer(result, many=True)
        return Response(serializer.data)

# ENDPOINTI 2 - CSV EXPORT
class VendorOrdersExportView(APIView):
    """
    GET /api/v1/vendor/orders/export/?format=csv
    Initiates async CSV export via Celery
    """
    permission_classes = [IsVendorAdmin]

    @extend_schema(
        tags=['Vendor Orders'],
        responses={
            202: OpenApiResponse(description='CSV export task queued.'),
            400: OpenApiResponse(description='Only CSV format is supported.'),
            404: OpenApiResponse(description='Vendor profile not found.'),
        },
    )

    def get(self, request):
        format_param = request.query_params.get('format', 'csv')

        try:
            export_data = VendorService.queue_order_export_for_user(
                request.user,
                format_param,
            )
        except UnsupportedExportFormatError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except VendorProfileNotFoundError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            export_data,
            status=status.HTTP_202_ACCEPTED,
        )

# ENDPOINTI 3 - CHECK EXPORT STATUS
class ExportStatusView(APIView):
    """
    GET /api/v1/vendor/export/status/?task_id=<task_id>
    Poll for export task status
    """
    permission_classes = [IsVendorAdmin]

    @extend_schema(
        tags=['Vendor Orders'],
        parameters=[
            OpenApiParameter(
                name='task_id',
                type=str,
                required=True,
                description='Celery task id returned by the export endpoint.',
            ),
        ],
        responses={
            status.HTTP_200_OK: inline_serializer(
                name='VendorExportStatusResponse',
                fields={
                    'task_id': serializers.CharField(),
                    'status': serializers.CharField(),
                    'result': serializers.DictField(required=False),
                    'download_url': serializers.CharField(required=False),
                    'error': serializers.CharField(required=False),
                },
            ),
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description='task_id query parameter is required.',
            ),
        },
        examples=[
            OpenApiExample(
                'Export status response',
                value={
                    'task_id': '2d4b3d5a-5876-4f18-9442-7ec3c7b4a0fb',
                    'status': 'SUCCESS',
                    'result': {'download_url': '/media/exports/orders.csv'},
                    'download_url': '/media/exports/orders.csv',
                },
                response_only=True,
            ),
        ],
    )
    def get(self, request):
        task_id = request.query_params.get('task_id')

        if not task_id:
            return Response(
                {'error': 'task_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(VendorService.get_export_status(task_id))
