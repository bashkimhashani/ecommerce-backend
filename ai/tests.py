from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from cart.models import Cart
from catalog.models import Brand, Category, Product, ProductVariant
from checkout.models import CheckoutSession
from orders.models import Order, OrderItem
from tenants.models import Tenant
from users.models import User

from .models import AIReport
from .services import SalesAggregator
from .tasks import generate_nightly_report


class AIReportTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='ai-report-acme',
            domain='ai-report-acme.example.com',
            plan='basic',
        )
        self.other_tenant = Tenant.objects.create(
            name='Other Store',
            slug='ai-report-other',
            domain='ai-report-other.example.com',
            plan='basic',
        )
        self.customer = User.objects.create_user(
            email='ai-report-customer@example.com',
            password='StrongPass123',
            first_name='Report',
            last_name='Customer',
            role='customer',
            tenant=self.tenant,
        )
        self.other_customer = User.objects.create_user(
            email='ai-report-other@example.com',
            password='StrongPass123',
            first_name='Other',
            last_name='Customer',
            role='customer',
            tenant=self.other_tenant,
        )
        self.variant = self._create_variant(self.tenant, 'Laptop Pro', 'LAPTOP')
        self.mouse_variant = self._create_variant(
            self.tenant,
            'Wireless Mouse',
            'MOUSE',
        )
        self.other_variant = self._create_variant(
            self.other_tenant,
            'Other Product',
            'OTHER',
        )

    def test_sales_aggregator_summarizes_tenant_orders_and_items(self):
        first_order = self._create_order(
            total='1200.00',
            idempotency_key='report-order-1',
        )
        self._create_item(first_order, self.variant, 'Laptop Pro', 1, '1000.00')
        self._create_item(
            first_order,
            self.mouse_variant,
            'Wireless Mouse',
            2,
            '100.00',
        )
        second_order = self._create_order(
            total='300.00',
            idempotency_key='report-order-2',
        )
        self._create_item(
            second_order,
            self.mouse_variant,
            'Wireless Mouse',
            3,
            '100.00',
        )
        cancelled_order = self._create_order(
            total='999.00',
            idempotency_key='report-cancelled',
        )
        Order.all_objects.filter(pk=cancelled_order.pk).update(
            status=Order.Status.CANCELLED,
        )
        self._create_order(
            user=self.other_customer,
            tenant=self.other_tenant,
            variant=self.other_variant,
            total='777.00',
            idempotency_key='other-tenant-order',
        )
        old_order = self._create_order(
            total='500.00',
            idempotency_key='old-order',
        )
        Order.all_objects.filter(pk=old_order.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=45),
        )

        summary = SalesAggregator().get_period_summary(self.tenant, days=30)

        self.assertEqual(summary['order_count'], 2)
        self.assertEqual(summary['total_revenue'], Decimal('1500.00'))
        self.assertEqual(summary['item_count'], 6)
        self.assertEqual(summary['top_products'][0]['product_name'], 'Wireless Mouse')
        self.assertEqual(summary['top_products'][0]['quantity_sold'], 5)
        self.assertEqual(summary['top_products'][1]['product_name'], 'Laptop Pro')

    @patch('ai.tasks.AIReportGenerator')
    def test_generate_nightly_report_logs_token_usage(self, generator_class):
        generator_class.return_value.generate.return_value = {
            'content': 'Revenue improved. Keep promoting Wireless Mouse.',
            'prompt_tokens': 123,
            'completion_tokens': 45,
        }
        order = self._create_order(
            total='1200.00',
            idempotency_key='token-report-order',
        )
        self._create_item(order, self.variant, 'Laptop Pro', 1, '1200.00')

        report_id = generate_nightly_report(self.tenant.id)

        report = AIReport.all_objects.get(pk=report_id)
        self.assertEqual(report.tenant, self.tenant)
        self.assertEqual(report.report_type, AIReport.ReportType.NIGHTLY_SALES)
        self.assertEqual(report.content, 'Revenue improved. Keep promoting Wireless Mouse.')
        self.assertEqual(report.prompt_tokens, 123)
        self.assertEqual(report.completion_tokens, 45)
        summary = generator_class.return_value.generate.call_args.args[0]
        self.assertEqual(summary['total_revenue'], Decimal('1200.00'))

    def _create_variant(self, tenant, name, sku):
        brand = Brand.all_objects.create(
            tenant=tenant,
            name=f'{name} Brand',
            slug=f'{sku.lower()}-brand',
        )
        category = Category.all_objects.create(
            tenant=tenant,
            name=f'{name} Category',
            slug=f'{sku.lower()}-category',
        )
        product = Product.all_objects.create(
            tenant=tenant,
            brand=brand,
            category=category,
            name=name,
            slug=sku.lower(),
            sku=sku,
            status=Product.Status.ACTIVE,
            base_price=Decimal('100.00'),
        )
        return ProductVariant.all_objects.create(
            tenant=tenant,
            product=product,
            variant_price=Decimal('100.00'),
            stock_quantity=10,
        )

    def _create_order(
        self,
        total,
        idempotency_key,
        user=None,
        tenant=None,
        variant=None,
    ):
        user = user or self.customer
        tenant = tenant or self.tenant
        cart = Cart.objects.create(
            user=user,
            tenant=tenant,
            status=Cart.Status.CHECKED_OUT,
        )
        checkout_session = CheckoutSession.objects.create(
            user=user,
            cart=cart,
            idempotency_key=idempotency_key,
            shipping_address={'city': 'Prishtina'},
            status=CheckoutSession.Status.READY,
            tenant=tenant,
        )
        order = Order.objects.create(
            user=user,
            checkout_session=checkout_session,
            shipping_address={'city': 'Prishtina'},
            subtotal=Decimal(total),
            total_amount=Decimal(total),
            tenant=tenant,
        )
        if variant:
            self._create_item(order, variant, variant.product.name, 1, total)
        return order

    def _create_item(self, order, variant, name, quantity, unit_price):
        unit_price = Decimal(unit_price)
        return OrderItem.objects.create(
            tenant=order.tenant,
            order=order,
            product_variant=variant,
            product_name=name,
            quantity=quantity,
            unit_price=unit_price,
            line_total=unit_price * quantity,
        )
