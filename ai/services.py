from decimal import Decimal
import json

from django.conf import settings
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from openai import OpenAI

from orders.models import Order, OrderItem


class AnalyticsQueryValidationError(ValueError):
    pass


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


class AnalyticsQueryResolver:
    allowed_metrics = {
        'total_revenue',
        'order_count',
        'items_sold',
        'top_products',
    }
    allowed_statuses = {choice.value for choice in Order.Status}
    max_days = 365
    max_limit = 10
    query_tool = {
        'type': 'function',
        'function': {
            'name': 'run_store_analytics_query',
            'description': (
                'Resolve a vendor store analytics question into one safe, '
                'allowlisted aggregate query.'
            ),
            'parameters': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'metric': {
                        'type': 'string',
                        'enum': sorted(allowed_metrics),
                    },
                    'days': {
                        'type': 'integer',
                        'minimum': 1,
                        'maximum': max_days,
                    },
                    'status': {
                        'type': 'string',
                        'enum': sorted(allowed_statuses),
                    },
                    'limit': {
                        'type': 'integer',
                        'minimum': 1,
                        'maximum': max_limit,
                    },
                },
                'required': ['metric', 'days'],
            },
        },
    }

    def __init__(self):
        client_options = {'api_key': settings.OPENAI_API_KEY}
        if settings.OPENAI_BASE_URL:
            client_options['base_url'] = settings.OPENAI_BASE_URL
        self.client = OpenAI(**client_options)

    def resolve(self, tenant, question):
        query = self.resolve_query(question)
        result = self.execute_query(tenant, query)
        return {
            'answer': self.format_answer(query, result),
            'query': query,
            'result': result,
        }

    def resolve_query(self, question):
        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'Convert the vendor question into exactly one '
                        'run_store_analytics_query function call. Do not '
                        'invent unsupported fields or filters.'
                    ),
                },
                {'role': 'user', 'content': question},
            ],
            tools=[self.query_tool],
            tool_choice={
                'type': 'function',
                'function': {'name': 'run_store_analytics_query'},
            },
            temperature=0,
        )
        tool_calls = response.choices[0].message.tool_calls or []
        if not tool_calls:
            raise AnalyticsQueryValidationError(
                'Could not resolve the question into a safe analytics query.',
            )

        arguments = tool_calls[0].function.arguments
        try:
            query = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise AnalyticsQueryValidationError(
                'Analytics query arguments were not valid JSON.',
            ) from exc

        return self.validate_query(query)

    def validate_query(self, query):
        allowed_keys = {'metric', 'days', 'status', 'limit'}
        unknown_keys = set(query) - allowed_keys
        if unknown_keys:
            raise AnalyticsQueryValidationError(
                'Analytics query contains unsupported parameters.',
            )

        metric = query.get('metric')
        if metric not in self.allowed_metrics:
            raise AnalyticsQueryValidationError(
                'Analytics metric is not allowed.',
            )

        days = query.get('days')
        if not isinstance(days, int) or days < 1 or days > self.max_days:
            raise AnalyticsQueryValidationError(
                'Analytics date range is not allowed.',
            )

        status = query.get('status')
        if status is not None and status not in self.allowed_statuses:
            raise AnalyticsQueryValidationError(
                'Analytics status filter is not allowed.',
            )

        limit = query.get('limit', 5)
        if not isinstance(limit, int) or limit < 1 or limit > self.max_limit:
            raise AnalyticsQueryValidationError(
                'Analytics result limit is not allowed.',
            )

        validated = {
            'metric': metric,
            'days': days,
            'limit': limit,
        }
        if status:
            validated['status'] = status
        return validated

    def execute_query(self, tenant, query):
        start_date = timezone.now() - timezone.timedelta(days=query['days'])
        orders = Order.all_objects.filter(
            tenant=tenant,
            created_at__gte=start_date,
        )
        if query.get('status'):
            orders = orders.filter(status=query['status'])
        else:
            orders = orders.exclude(status=Order.Status.CANCELLED)

        metric = query['metric']
        if metric == 'total_revenue':
            value = orders.aggregate(
                value=Coalesce(
                    Sum('total_amount'),
                    Decimal('0.00'),
                    output_field=Order._meta.get_field('total_amount'),
                ),
            )['value']
            return {'value': str(value)}

        if metric == 'order_count':
            return {'value': orders.count()}

        order_items = OrderItem.all_objects.filter(
            tenant=tenant,
            order__in=orders,
        )
        if metric == 'items_sold':
            value = order_items.aggregate(
                value=Coalesce(Sum('quantity'), 0),
            )['value']
            return {'value': value or 0}

        if metric == 'top_products':
            products = list(
                order_items.values('product_name')
                .annotate(
                    quantity_sold=Coalesce(Sum('quantity'), 0),
                    revenue=Coalesce(
                        Sum('line_total'),
                        Decimal('0.00'),
                        output_field=OrderItem._meta.get_field('line_total'),
                    ),
                )
                .order_by('-quantity_sold', '-revenue', 'product_name')[
                    :query['limit']
                ],
            )
            return {
                'products': [
                    {
                        'product_name': product['product_name'],
                        'quantity_sold': product['quantity_sold'],
                        'revenue': str(product['revenue']),
                    }
                    for product in products
                ],
            }

        raise AnalyticsQueryValidationError('Analytics metric is not allowed.')

    def format_answer(self, query, result):
        days_text = f"last {query['days']} days"
        status_text = (
            f" with status {query['status']}"
            if query.get('status')
            else ''
        )
        metric = query['metric']

        if metric == 'top_products':
            products = result['products']
            if not products:
                return f'No products were sold in the {days_text}{status_text}.'
            top_product = products[0]
            return (
                f"Top product in the {days_text}{status_text}: "
                f"{top_product['product_name']} with "
                f"{top_product['quantity_sold']} units sold."
            )

        labels = {
            'total_revenue': 'Total revenue',
            'order_count': 'Order count',
            'items_sold': 'Items sold',
        }
        return (
            f"{labels[metric]} for the {days_text}{status_text}: "
            f"{result['value']}."
        )
