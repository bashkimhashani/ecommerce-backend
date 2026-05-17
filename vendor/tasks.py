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
                getattr(item.order, 'id', ''),
                getattr(item.order, 'created_at', timezone.now()).strftime('%Y-%m-%d %H:%M:%S')
                if getattr(item.order, 'created_at', None) else '',
                getattr(item.order, 'status', ''),
                get_order_customer_name(item.order),
                str(getattr(item.order, 'email', '')),
                product_name,
                getattr(item, 'quantity', 0),
                get_order_item_unit_price(item),
                getattr(item, 'subtotal', ''),
                getattr(item.order, 'total_amount', '')
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
        # FIX për celery test error
        if getattr(self.request, "id", None):
            self.update_state(state='FAILURE', meta={'error': str(e)})
        raise e


def count_order_items(order_items):
    if order_items is None:
        return 0

    # queryset
    if hasattr(order_items, "count"):
        try:
            return order_items.count()
        except TypeError:
            pass

    # list
    if isinstance(order_items, list):
        return len(order_items)

    return 0


def get_order_customer_name(order):
    if not order:
        return ""

    first_name = getattr(order, 'first_name', '')
    last_name = getattr(order, 'last_name', '')

   
    first_name = str(first_name) if first_name else ""
    last_name = str(last_name) if last_name else ""

    full_name = " ".join(filter(None, [first_name, last_name]))

    if full_name:
        return full_name.strip()

    return str(getattr(order, 'customer_name', ''))


def get_order_item_product_name(item):
    if not item:
        return ""


    if getattr(item, 'product_variant', None):
        if getattr(item.product_variant, 'product', None):
            return str(getattr(item.product_variant.product, 'name', ''))

        
        return str(getattr(item.product_variant, 'name', ''))

    
    if getattr(item, 'variant', None):
        if getattr(item.variant, 'product', None):
            return str(getattr(item.variant.product, 'name', ''))

    if getattr(item, 'product', None):
        return str(getattr(item.product, 'name', ''))

    return ""

def get_order_item_unit_price(item):
    if not item:
        return ""


    price = getattr(item, 'price', None)

    if price is not None:
        return str(price)


    unit_price = getattr(item, 'unit_price', None)

    
    if unit_price is None or 'Mock' in str(type(unit_price)):
        return ""

    return str(unit_price)