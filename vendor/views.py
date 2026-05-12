from decimal import Decimal

from django.apps import apps
from django.core.cache import cache
from django.db.models import Count, F, Sum
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import OpenApiResponse, extend_schema

from inventory.models import Inventory
from inventory.serializers import InventorySerializer
from users.permissions import IsVendorAdmin
from .models import VendorProfile
from .serializers import OrderSummarySerializer


def get_vendor_for_request(request):
    return VendorProfile.objects.get(
        user=request.user,
        tenant=request.user.tenant,
    )


def get_order_model():
    try:
        return apps.get_model('orders', 'Order')
    except LookupError:
        return None


def get_order_item_model():
    try:
        return apps.get_model('orders', 'OrderItem')
    except LookupError:
        return None


def get_vendor_order_queryset(vendor):
    Order = get_order_model()

    if Order is None:
        return None

    return Order.objects.filter(tenant=vendor.tenant)


def serialize_decimal(value):
    return str(value or Decimal('0.00'))


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
        try:
            vendor = get_vendor_for_request(request)
        except VendorProfile.DoesNotExist:
            return Response(
                {'error': 'Vendor profile not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        inventory = Inventory.all_objects.filter(
            tenant=vendor.tenant,
            vendor=vendor,
        ).select_related(
            'product_variant',
            'product_variant__product',
        )
        low_stock_items = inventory.filter(
            quantity__lte=F('low_stock_threshold'),
        )
        orders = get_vendor_order_queryset(vendor)
        order_count = 0
        revenue = Decimal('0.00')

        if orders is not None:
            order_totals = orders.aggregate(
                order_count=Count('id'),
                revenue=Sum('total_amount'),
            )
            order_count = order_totals['order_count'] or 0
            revenue = order_totals['revenue'] or Decimal('0.00')

        return Response({
            'order_count': order_count,
            'revenue': serialize_decimal(revenue),
            'low_stock_alerts': low_stock_items.count(),
            'low_stock_items': InventorySerializer(low_stock_items, many=True).data,
        })


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
        try:
            vendor = get_vendor_for_request(request)
        except VendorProfile.DoesNotExist:
            return Response(
                {'error': 'Vendor profile not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        inventory = Inventory.all_objects.filter(
            tenant=vendor.tenant,
            vendor=vendor,
        ).select_related(
            'product_variant',
            'product_variant__product',
        ).order_by('product_variant__product__name', 'id')
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
        try:
            vendor = get_vendor_for_request(request)
        except VendorProfile.DoesNotExist:
            return Response(
                {'error': 'Vendor profile not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            inventory = Inventory.all_objects.select_related(
                'product_variant',
                'product_variant__product',
            ).get(
                id=pk,
                tenant=vendor.tenant,
                vendor=vendor,
            )
        except Inventory.DoesNotExist:
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
        serializer.save()
        return Response(serializer.data)


class VendorOrderSummaryView(APIView):
    """
    GET /api/v1/vendor/orders/summary/
    Returns order counts grouped by status for the authenticated vendor
    """
    permission_classes = [IsVendorAdmin]
    
    def get(self, request):
        # Get vendor profile
        try:
            vendor = get_vendor_for_request(request)
        except VendorProfile.DoesNotExist:
            return Response(
                {'error': 'Vendor profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check cache first (5 minutes TTL)
        cache_key = f'vendor_order_summary_{vendor.id}'
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return Response(cached_data)
        
        OrderItem = get_order_item_model()

        if OrderItem is None:
            cache.set(cache_key, [], 300)
            return Response([])

        order_items = OrderItem.objects.filter(
            product__inventory_items__vendor=vendor,
            order__tenant=vendor.tenant
        ).select_related('order')
        
        # Aggregate by order status
        summary = order_items.values('order__status').annotate(
            count=Count('order_id', distinct=True),
            total_amount=Sum('subtotal')
        )
        
        # Format response
        result = []
        for item in summary:
            result.append({
                'status': item['order__status'],
                'count': item['count'],
                'total_amount': str(item['total_amount'] or '0')
            })
        
        # Cache for 5 minutes
        cache.set(cache_key, result, 300)
        
        serializer = OrderSummarySerializer(result, many=True)
        return Response(serializer.data)
    
# ENDPOINTI 2 - CSV EXPORT 
class VendorOrdersExportView(APIView):
    """
    GET /api/v1/vendor/orders/export/?format=csv
    Initiates async CSV export via Celery
    """
    permission_classes = [IsVendorAdmin]
    
    def get(self, request):
        format_param = request.query_params.get('format', 'csv')
        
        if format_param != 'csv':
            return Response(
                {'error': 'Only CSV format is supported'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            vendor = get_vendor_for_request(request)
        except VendorProfile.DoesNotExist:
            return Response(
                {'error': 'Vendor profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        from .tasks import export_vendor_orders_csv
        
        task = export_vendor_orders_csv.delay(vendor.id, request.user.id)
        
        cache_key = f'vendor_export_task_{request.user.id}'
        cache.set(cache_key, task.id, 3600)
        
        return Response({
            'task_id': task.id,
            'status': 'queued',
            'message': 'CSV export has been queued',
            'poll_url': f'/api/v1/vendor/export/status/?task_id={task.id}'
        }, status=status.HTTP_202_ACCEPTED)

# ENDPOINTI 3 - CHECK EXPORT STATUS 
class ExportStatusView(APIView):
    """
    GET /api/v1/vendor/export/status/?task_id=<task_id>
    Poll for export task status
    """
    permission_classes = [IsVendorAdmin]
    
    def get(self, request):
        task_id = request.query_params.get('task_id')
        
        if not task_id:
            return Response(
                {'error': 'task_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from celery.result import AsyncResult
        task = AsyncResult(task_id)
        
        response_data = {
            'task_id': task_id,
            'status': task.state,
        }
        
        if task.state == 'SUCCESS':
            response_data['result'] = task.result
            response_data['download_url'] = task.result.get('download_url')
        elif task.state == 'FAILURE':
            response_data['error'] = str(task.info)
        
        return Response(response_data)
