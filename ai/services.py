from decimal import Decimal
import json
import uuid

from django.conf import settings
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from openai import OpenAI

from catalog.models import Product
from orders.models import Order, OrderItem

from .history import ChatHistoryStore


class AnalyticsQueryValidationError(ValueError):
    pass


class ProductContextRetriever:
    def get_relevant_products(self, query, tenant=None, limit=5):
        keywords = self.extract_keywords(query)
        products = Product.all_objects.filter(status=Product.Status.ACTIVE)
        if tenant:
            products = products.filter(tenant=tenant)

        candidates = products.select_related('brand', 'category').prefetch_related(
            'images',
        )[:100]
        scored_products = []
        for product in candidates:
            searchable_text = ' '.join(
                [
                    product.name,
                    product.sku,
                    product.description,
                    product.brand.name,
                    product.category.name,
                    json.dumps(product.tech_specs),
                ],
            ).lower()
            score = sum(1 for keyword in keywords if keyword in searchable_text)
            if score:
                scored_products.append((score, product))

        scored_products.sort(key=lambda item: (-item[0], item[1].name))
        return [
            self.serialize_product(product)
            for _, product in scored_products[:limit]
        ]

    def extract_keywords(self, query):
        ignored_words = {
            'a',
            'about',
            'an',
            'and',
            'for',
            'i',
            'me',
            'of',
            'please',
            'recommend',
            'show',
            'the',
            'to',
            'with',
        }
        return [
            word.strip('.,!?;:()[]{}"\'').lower()
            for word in query.split()
            if len(word.strip('.,!?;:()[]{}"\'').lower()) > 2
            and word.strip('.,!?;:()[]{}"\'').lower() not in ignored_words
        ]

    def serialize_product(self, product):
        return {
            'id': product.id,
            'name': product.name,
            'slug': product.slug,
            'sku': product.sku,
            'brand': product.brand.name,
            'category': product.category.name,
            'price': str(product.base_price),
            'thumbnail': self.get_thumbnail(product),
            'description': product.description,
            'tech_specs': product.tech_specs,
        }

    def get_thumbnail(self, product):
        primary_image = next(
            (image for image in product.images.all() if image.is_primary),
            None,
        )
        if primary_image is None:
            primary_image = next(iter(product.images.all()), None)
        if primary_image is None:
            return ''

        image_field = (
            primary_image.thumbnail
            or primary_image.medium
            or primary_image.image
        )
        if not image_field:
            return ''
        return image_field.url


class ChatService:
    def __init__(self):
        client_options = {'api_key': settings.OPENAI_API_KEY}
        if settings.OPENAI_BASE_URL:
            client_options['base_url'] = settings.OPENAI_BASE_URL
        self.client = OpenAI(**client_options)

    def complete(self, messages, system_prompt):
        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {'role': 'system', 'content': system_prompt},
                *messages,
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content


class ChatWorkflowService:
    history_store_class = ChatHistoryStore
    product_retriever_class = ProductContextRetriever
    chat_service_class = ChatService

    def respond(self, message, session_id=None, tenant=None):
        session_id = session_id or uuid.uuid4().hex
        history_store = self.history_store_class()
        history = history_store.get_history(session_id)
        products = self.product_retriever_class().get_relevant_products(
            message,
            tenant=tenant,
        )
        messages = [
            *history,
            {'role': 'user', 'content': message},
        ][-20:]
        used_fallback = False

        try:
            assistant_message = self.chat_service_class().complete(
                messages=messages,
                system_prompt=self.build_system_prompt(products),
            )
        except Exception:
            used_fallback = True
            assistant_message = self.build_fallback_answer(products)

        history_store.append_turn(
            session_id=session_id,
            tenant=tenant,
            user_message=message,
            assistant_message=assistant_message,
        )
        return {
            'session_id': session_id,
            'message': assistant_message,
            'used_fallback': used_fallback,
            'products': products,
        }

    def build_system_prompt(self, products):
        return (
            f'{settings.OPENAI_CHAT_SYSTEM_PROMPT}\n\n'
            f'Catalog context:\n{self.format_products(products)}'
        )

    def format_products(self, products):
        if not products:
            return 'No matching catalog products were found for this question.'
        return '\n'.join(
            (
                f"- {product['name']} ({product['brand']}): "
                f"${product['price']}; category {product['category']}; "
                f"SKU {product['sku']}; specs {product['tech_specs']}"
            )
            for product in products
        )

    def build_fallback_answer(self, products):
        if not products:
            return (
                'I can help with tech products, prices, specs, cart, checkout, '
                'and account questions. I could not find a matching catalog '
                'item for that message, so try asking for a product type like '
                'laptop, phone, keyboard, or monitor.'
            )

        product_lines = [
            f"{product['name']} by {product['brand']} at ${product['price']}"
            for product in products[:3]
        ]
        return (
            'Here are a few catalog matches I can recommend: '
            f"{'; '.join(product_lines)}. "
            'Tell me your budget or preferred specs and I can narrow it down.'
        )


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

        try:
            query = json.loads(tool_calls[0].function.arguments)
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
