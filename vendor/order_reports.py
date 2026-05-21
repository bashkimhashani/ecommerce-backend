from decimal import Decimal

from django.apps import apps
from django.db.models import Count, Sum


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


def order_item_field_names(order_item_model):
    return {field.name for field in order_item_model._meta.get_fields()}


def order_item_amount_field(order_item_model):
    field_names = order_item_field_names(order_item_model)

    if 'subtotal' in field_names:
        return 'subtotal'

    return 'line_total'


def vendor_order_item_filter(order_item_model, vendor):
    field_names = order_item_field_names(order_item_model)

    if 'product_variant' in field_names:
        return {'product_variant__inventory_items__vendor': vendor}

    if 'variant' in field_names:
        return {'variant__inventory_items__vendor': vendor}

    if 'product' in field_names:
        return {'product__variants__inventory_items__vendor': vendor}

    return {}


def vendor_order_items(vendor):
    OrderItem = get_order_item_model()

    if OrderItem is None:
        return None

    vendor_filter = vendor_order_item_filter(OrderItem, vendor)

    if not vendor_filter:
        return OrderItem.objects.none()

    return OrderItem.objects.filter(
        order__tenant=vendor.tenant,
        **vendor_filter,
    ).select_related('order')


def serialize_decimal(value):
    return str(value or Decimal('0.00'))


def vendor_order_summary_rows(vendor):
    order_items = vendor_order_items(vendor)
    OrderItem = get_order_item_model()

    if order_items is None or OrderItem is None:
        return []

    amount_field = order_item_amount_field(OrderItem)

    summary = order_items.values('order__status').annotate(
        count=Count('order_id', distinct=True),
        total_amount=Sum(amount_field),
    ).order_by('order__status')

    return [
        {
            'status': item['order__status'],
            'count': item['count'],
            'total_amount': serialize_decimal(item['total_amount']),
        }
        for item in summary
    ]


def vendor_order_totals(vendor):
    order_items = vendor_order_items(vendor)
    OrderItem = get_order_item_model()

    if order_items is None or OrderItem is None:
        return {
            'order_count': 0,
            'revenue': Decimal('0.00'),
        }

    amount_field = order_item_amount_field(OrderItem)

    totals = order_items.aggregate(
        order_count=Count('order_id', distinct=True),
        revenue=Sum(amount_field),
    )

    return {
        'order_count': totals['order_count'] or 0,
        'revenue': totals['revenue'] or Decimal('0.00'),
    }
