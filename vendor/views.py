from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Count, Sum
from django.core.cache import cache
from .models import VendorProfile
from .serializers import OrderSummarySerializer

class VendorOrderSummaryView(APIView):
    """
    GET /api/v1/vendor/orders/summary/
    Returns order counts grouped by status for the authenticated vendor
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Get vendor profile
        try:
            vendor = VendorProfile.objects.get(user=request.user)
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
        
        # Get all order items from this vendor's products
        # Note: This assumes OrderItem model exists with product and order relations
        from orders.models import OrderItem
        
        order_items = OrderItem.objects.filter(
            product__inventory__vendor=vendor,
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
