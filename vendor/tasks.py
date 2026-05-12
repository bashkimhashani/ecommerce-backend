from celery import shared_task
import csv
import io
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from .models import VendorProfile
from .order_reports import vendor_order_items
from django.contrib.auth import get_user_model

User = get_user_model()

@shared_task(bind=True)
def export_vendor_orders_csv(self, vendor_id, user_id):
    try:
        vendor = VendorProfile.objects.get(id=vendor_id)
        User.objects.get(id=user_id)
        order_items = vendor_order_items(vendor)

        if order_items is None:
            order_items = []
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow([
            'Order ID', 'Order Date', 'Status', 'Customer Name', 'Customer Email',
            'Product Name', 'Quantity', 'Unit Price', 'Subtotal', 'Total Order Amount'
        ])
        
        for item in order_items:
            product_name = get_order_item_product_name(item)
            writer.writerow([
                item.order.id,
                item.order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                item.order.status,
                get_order_customer_name(item.order),
                getattr(item.order, 'email', ''),
                product_name,
                item.quantity,
                get_order_item_unit_price(item),
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
            'row_count': count_order_items(order_items),
            'exported_at': str(timezone.now())
        }
        
    except Exception as e:
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise e


def count_order_items(order_items):
    if hasattr(order_items, 'count'):
        return order_items.count()
    return len(order_items)


def get_order_customer_name(order):
    full_name = ' '.join(
        value for value in [
            getattr(order, 'first_name', ''),
            getattr(order, 'last_name', ''),
        ]
        if value
    )
    return full_name or getattr(order, 'customer_name', '')


def get_order_item_product_name(item):
    if hasattr(item, 'product_variant'):
        return item.product_variant.product.name
    if hasattr(item, 'variant'):
        return item.variant.product.name
    if hasattr(item, 'product'):
        return item.product.name
    return ''


def get_order_item_unit_price(item):
    return getattr(item, 'price', getattr(item, 'unit_price', ''))
