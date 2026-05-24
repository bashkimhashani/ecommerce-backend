from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from openai import OpenAI

from orders.models import Order, OrderItem


class SalesAggregator:
    def get_period_summary(self, tenant, days=30):
        start_date = timezone.now() - timezone.timedelta(days=days)
        orders = Order.all_objects.filter(
            tenant=tenant,
            created_at__gte=start_date,
        ).exclude(
            status=Order.Status.CANCELLED,
        )
        order_items = OrderItem.all_objects.filter(
            tenant=tenant,
            order__in=orders,
        )

        totals = orders.aggregate(
            order_count=Count('id'),
            total_revenue=Coalesce(
                Sum('total_amount'),
                Decimal('0.00'),
                output_field=Order._meta.get_field('total_amount'),
            ),
        )
        item_totals = order_items.aggregate(
            item_count=Coalesce(Sum('quantity'), 0),
        )
        top_products = list(
            order_items.values('product_name')
            .annotate(
                quantity_sold=Coalesce(Sum('quantity'), 0),
                revenue=Coalesce(
                    Sum('line_total'),
                    Decimal('0.00'),
                    output_field=OrderItem._meta.get_field('line_total'),
                ),
            )
            .order_by('-quantity_sold', '-revenue', 'product_name')[:5],
        )

        return {
            'tenant_id': tenant.id,
            'tenant_name': tenant.name,
            'days': days,
            'order_count': totals['order_count'],
            'total_revenue': totals['total_revenue'],
            'item_count': item_totals['item_count'] or 0,
            'top_products': top_products,
        }


class AIReportGenerator:
    system_prompt = (
        'You are an ecommerce sales analyst. Write a concise vendor-facing '
        'nightly sales report from the provided store metrics. Include '
        'revenue, order volume, top products, and one practical recommendation.'
    )

    def __init__(self):
        client_options = {'api_key': settings.OPENAI_API_KEY}
        if settings.OPENAI_BASE_URL:
            client_options['base_url'] = settings.OPENAI_BASE_URL
        self.client = OpenAI(**client_options)

    def generate(self, summary):
        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {'role': 'system', 'content': self.system_prompt},
                {'role': 'user', 'content': self.build_prompt(summary)},
            ],
            temperature=0.2,
        )
        usage = getattr(response, 'usage', None)
        message = response.choices[0].message.content

        return {
            'content': message,
            'prompt_tokens': getattr(usage, 'prompt_tokens', 0) if usage else 0,
            'completion_tokens': (
                getattr(usage, 'completion_tokens', 0) if usage else 0
            ),
        }

    def build_prompt(self, summary):
        top_products = summary['top_products'] or []
        products_text = '\n'.join(
            (
                f"- {product['product_name']}: "
                f"{product['quantity_sold']} units, "
                f"{product['revenue']} revenue"
            )
            for product in top_products
        ) or '- No product sales in this period.'

        return (
            f"Tenant: {summary['tenant_name']}\n"
            f"Period: last {summary['days']} days\n"
            f"Orders: {summary['order_count']}\n"
            f"Items sold: {summary['item_count']}\n"
            f"Revenue: {summary['total_revenue']}\n"
            f"Top products:\n{products_text}"
        )
