from celery import shared_task
import csv
import io
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from .models import VendorProfile
from django.contrib.auth import get_user_model

User = get_user_model()

@shared_task(bind=True)
def export_vendor_orders_csv(self, vendor_id, user_id):
    try:
        vendor = VendorProfile.objects.get(id=vendor_id)
        user = User.objects.get(id=user_id)
        
        from orders.models import OrderItem
        
        order_items = OrderItem.objects.filter(
            product__inventory__vendor=vendor,
            order__tenant=vendor.tenant
        ).select_related('order', 'product')
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow([
            'Order ID', 'Order Date', 'Status', 'Customer Name', 'Customer Email',
            'Product Name', 'Quantity', 'Unit Price', 'Subtotal', 'Total Order Amount'
        ])
        
        for item in order_items:
            writer.writerow([
                item.order.id,
                item.order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                item.order.status,
                f"{item.order.first_name} {item.order.last_name}",
                item.order.email,
                item.product.name,
                item.quantity,
                item.price,
                item.subtotal,
                item.order.total_amount
            ])
        
        filename = f"exports/vendor_{vendor.id}_orders_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_content = ContentFile(output.getvalue().encode('utf-8'))
        saved_path = default_storage.save(filename, file_content)
        download_url = default_storage.url(saved_path)
        
        return {
            'status': 'success',
            'file_path': saved_path,
            'download_url': download_url,
            'row_count': order_items.count(),
            'exported_at': str(timezone.now())
        }
        
    except Exception as e:
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise e