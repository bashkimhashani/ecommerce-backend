from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import Mock, patch

from ai.models import AIReport
from catalog.models import Brand, Category, Product, ProductVariant
from inventory.models import Inventory
from tenants.models import Tenant
from .order_reports import vendor_order_summary_rows
from .models import VendorProfile

User = get_user_model()


class VendorInventoryEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.tenant = Tenant.objects.create(
            name='Test Tenant',
            slug='test-tenant',
            domain='test.local',
        )

        self.other_tenant = Tenant.objects.create(
            name='Other Tenant',
            slug='other-tenant',
            domain='other.local',
        )

        self.user = User.objects.create_user(
            email='vendor@test.com',
            password='testpass123',
            first_name='Vendor',
            last_name='Admin',
            role='vendor_admin',
            tenant=self.tenant,
        )

        self.vendor = VendorProfile.objects.create(
            user=self.user,
            tenant=self.tenant,
            store_name='Test Store',
            contact_email='store@test.com',
        )

        self.brand = Brand.all_objects.create(
            tenant=self.tenant,
            name='Apple',
            slug='apple',
        )

        self.category = Category.objects.create(
            tenant=self.tenant,
            name='Laptops',
            slug='laptops',
        )

        self.product = Product.all_objects.create(
            tenant=self.tenant,
            name='MacBook Air',
            slug='macbook-air',
            sku='MBA-001',
            brand=self.brand,
            category=self.category,
            status=Product.Status.ACTIVE,
            base_price='1099.00',
        )

        self.variant = ProductVariant.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            color='Silver',
            storage='512GB',
            ram='16GB',
            variant_price='1199.00',
            stock_quantity=4,
        )

        self.inventory = Inventory.all_objects.create(
            tenant=self.tenant,
            vendor=self.vendor,
            product_variant=self.variant,
            quantity=4,
            low_stock_threshold=5,
        )

        self.client.force_authenticate(user=self.user)

    def test_dashboard_summary_returns_order_revenue_and_low_stock_alerts(self):
        response = self.client.get('/api/v1/vendor/dashboard/summary/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['order_count'], 0)
        self.assertEqual(response.data['revenue'], '0.00')
        self.assertEqual(response.data['low_stock_alerts'], 1)
        self.assertEqual(
            response.data['low_stock_items'][0]['id'],
            self.inventory.id,
        )

    def test_inventory_list_returns_vendor_tenant_items(self):
        other_user = User.objects.create_user(
            email='other-vendor@test.com',
            password='testpass123',
            first_name='Other',
            last_name='Vendor',
            role='vendor_admin',
            tenant=self.other_tenant,
        )

        other_vendor = VendorProfile.objects.create(
            user=other_user,
            tenant=self.other_tenant,
            store_name='Other Store',
            contact_email='other-store@test.com',
        )

        other_brand = Brand.all_objects.create(
            tenant=self.other_tenant,
            name='Dell',
            slug='dell',
        )

        other_category = Category.objects.create(
            tenant=self.other_tenant,
            name='Laptops',
            slug='other-laptops',
        )

        other_product = Product.all_objects.create(
            tenant=self.other_tenant,
            name='Dell XPS',
            slug='dell-xps',
            sku='XPS-001',
            brand=other_brand,
            category=other_category,
            status=Product.Status.ACTIVE,
            base_price='1299.00',
        )

        other_variant = ProductVariant.all_objects.create(
            tenant=self.other_tenant,
            product=other_product,
            variant_price='1299.00',
            stock_quantity=20,
        )

        Inventory.all_objects.create(
            tenant=self.other_tenant,
            vendor=other_vendor,
            product_variant=other_variant,
            quantity=20,
            low_stock_threshold=5,
        )

        response = self.client.get('/api/v1/vendor/inventory/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.inventory.id)
        self.assertEqual(response.data[0]['product_name'], 'MacBook Air')
        self.assertEqual(
            response.data[0]['variant_name'],
            'Silver / 512GB / 16GB',
        )
        self.assertTrue(response.data[0]['is_low_stock'])

    def test_inventory_patch_updates_quantity(self):
        response = self.client.patch(
            f'/api/v1/vendor/inventory/{self.inventory.id}/',
            {'quantity': 8},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.inventory.refresh_from_db()

        self.assertEqual(self.inventory.quantity, 8)
        self.assertFalse(response.data['is_low_stock'])

    def test_inventory_patch_rejects_negative_quantity(self):
        response = self.client.patch(
            f'/api/v1/vendor/inventory/{self.inventory.id}/',
            {'quantity': -1},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customer_cannot_access_vendor_inventory(self):
        customer = User.objects.create_user(
            email='customer@test.com',
            password='testpass123',
            first_name='Normal',
            last_name='Customer',
            role='customer',
            tenant=self.tenant,
        )

        self.client.force_authenticate(user=customer)

        response = self.client.get('/api/v1/vendor/inventory/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('vendor.views.vendor_order_summary_rows')
    def test_order_summary_endpoint_returns_grouped_status_counts(
        self,
        mock_summary,
    ):
        cache.clear()

        mock_summary.return_value = [
            {'status': 'paid', 'count': 2, 'total_amount': '250.00'},
            {'status': 'shipped', 'count': 1, 'total_amount': '80.00'},
        ]

        response = self.client.get('/api/v1/vendor/orders/summary/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['status'], 'paid')
        self.assertEqual(response.data[0]['count'], 2)
        self.assertEqual(
            str(response.data[0]['total_amount']),
            '250.00',
        )

        mock_summary.assert_called_once_with(self.vendor)

    @patch('vendor.tasks.export_vendor_orders_csv.delay')
    def test_orders_export_queues_csv_task(self, mock_delay):
        mock_task = Mock()
        mock_task.id = 'export-task-123'

        mock_delay.return_value = mock_task

        response = self.client.get(
            '/api/v1/vendor/orders/export/?format=csv'
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_202_ACCEPTED,
        )

        self.assertEqual(
            response.data['task_id'],
            'export-task-123',
        )

        self.assertEqual(response.data['status'], 'queued')

        mock_delay.assert_called_once_with(
            self.vendor.id,
            self.user.id,
        )

    def test_orders_export_rejects_non_csv_format(self):
        response = self.client.get(
            '/api/v1/vendor/orders/export/?format=pdf'
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_latest_report_returns_tenant_scoped_newest_report(self):
        old_report = AIReport.all_objects.create(
            tenant=self.tenant,
            report_type=AIReport.ReportType.NIGHTLY_SALES,
            content='Old report',
            prompt_tokens=1,
            completion_tokens=2,
        )
        latest_report = AIReport.all_objects.create(
            tenant=self.tenant,
            report_type=AIReport.ReportType.NIGHTLY_SALES,
            content='Latest report',
            prompt_tokens=10,
            completion_tokens=20,
        )
        other_report = AIReport.all_objects.create(
            tenant=self.other_tenant,
            report_type=AIReport.ReportType.NIGHTLY_SALES,
            content='Other tenant report',
            prompt_tokens=100,
            completion_tokens=200,
        )

        response = self.client.get('/api/v1/vendor/reports/latest/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], latest_report.id)
        self.assertEqual(response.data['content'], 'Latest report')
        self.assertNotEqual(response.data['id'], old_report.id)
        self.assertNotEqual(response.data['id'], other_report.id)

    def test_latest_report_returns_no_content_when_missing(self):
        response = self.client.get('/api/v1/vendor/reports/latest/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_latest_report_requires_vendor_admin(self):
        customer = User.objects.create_user(
            email='report-customer@test.com',
            password='testpass123',
            first_name='Report',
            last_name='Customer',
            role='customer',
            tenant=self.tenant,
        )
        self.client.force_authenticate(user=customer)

        response = self.client.get('/api/v1/vendor/reports/latest/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class FakeField:
    def __init__(self, name):
        self.name = name


class FakeOrderItemMeta:
    @staticmethod
    def get_fields():
        return [
            FakeField('order'),
            FakeField('product_variant'),
            FakeField('subtotal'),
        ]


class FakeSummaryValues:
    def __init__(self):
        self.values_args = None
        self.annotate_kwargs = None
        self.order_by_args = None

    def annotate(self, **kwargs):
        self.annotate_kwargs = kwargs
        return self

    def order_by(self, *args):
        self.order_by_args = args

        return [
            {
                'order__status': 'paid',
                'count': 2,
                'total_amount': 250,
            },
            {
                'order__status': 'shipped',
                'count': 1,
                'total_amount': 80,
            },
        ]


class FakeOrderItemQuerySet:
    def __init__(self):
        self.select_related_args = None
        self.summary_values = FakeSummaryValues()

    def select_related(self, *args):
        self.select_related_args = args
        return self

    def values(self, *args):
        self.summary_values.values_args = args
        return self.summary_values


class FakeOrderItemManager:
    def __init__(self):
        self.filter_kwargs = None
        self.queryset = FakeOrderItemQuerySet()

    def filter(self, **kwargs):
        self.filter_kwargs = kwargs
        return self.queryset


class FakeOrderItemModel:
    _meta = FakeOrderItemMeta()
    objects = FakeOrderItemManager()


class VendorOrderReportHelperTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Reports Tenant',
            slug='reports-tenant',
            domain='reports.local',
        )

        self.user = User.objects.create_user(
            email='reports-vendor@test.com',
            password='testpass123',
            first_name='Reports',
            last_name='Vendor',
            role='vendor_admin',
            tenant=self.tenant,
        )

        self.vendor = VendorProfile.objects.create(
            user=self.user,
            tenant=self.tenant,
            store_name='Reports Store',
            contact_email='reports-store@test.com',
        )

    @patch('vendor.order_reports.get_order_item_model')
    def test_summary_helper_groups_by_order_status_for_vendor_items(
        self,
        mock_model,
    ):
        FakeOrderItemModel.objects = FakeOrderItemManager()

        mock_model.return_value = FakeOrderItemModel

        rows = vendor_order_summary_rows(self.vendor)

        self.assertEqual(
            rows,
            [
                {
                    'status': 'paid',
                    'count': 2,
                    'total_amount': '250',
                },
                {
                    'status': 'shipped',
                    'count': 1,
                    'total_amount': '80',
                },
            ],
        )

        self.assertEqual(
            FakeOrderItemModel.objects.filter_kwargs,
            {
                'order__tenant': self.tenant,
                'product_variant__inventory_items__vendor': self.vendor,
            },
        )

        queryset = FakeOrderItemModel.objects.queryset

        self.assertEqual(
            queryset.select_related_args,
            ('order',),
        )

        self.assertEqual(
            queryset.summary_values.values_args,
            ('order__status',),
        )

        self.assertEqual(
            queryset.summary_values.order_by_args,
            ('order__status',),
        )

    def test_summary_helper_returns_empty_list_when_no_orders(self):
        with patch('vendor.order_reports.get_order_item_model') as mock_model:
            mock_model.return_value = None

            rows = vendor_order_summary_rows(self.vendor)

            self.assertEqual(rows, [])


class VendorOrderExportTaskTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.tenant = Tenant.objects.create(
            name='Export Tenant',
            slug='export-tenant',
            domain='export.local',
        )

        self.user = User.objects.create_user(
            email='export@test.com',
            password='testpass123',
            first_name='Export',
            last_name='Vendor',
            role='vendor_admin',
            tenant=self.tenant,
        )

        self.vendor = VendorProfile.objects.create(
            user=self.user,
            tenant=self.tenant,
            store_name='Export Store',
            contact_email='export-store@test.com',
        )

        self.client.force_authenticate(user=self.user)

    @patch('vendor.tasks.default_storage.url')
    @patch('vendor.tasks.default_storage.save')
    @patch('vendor.tasks.vendor_order_items')
    def test_export_task_creates_csv_with_correct_headers(
        self,
        mock_order_items,
        mock_storage_save,
        mock_storage_url,
    ):
        from vendor.tasks import export_vendor_orders_csv

        mock_product = Mock()
        mock_product.name = 'MacBook Pro'

        mock_variant = Mock()
        mock_variant.product = mock_product

        mock_item = Mock()

        mock_item.order.id = 123
        mock_item.order.created_at = timezone.now()
        mock_item.order.status = 'paid'
        mock_item.order.total_amount = '150.00'
        mock_item.order.email = 'customer@test.com'

        mock_item.quantity = 2
        mock_item.subtotal = '100.00'

        mock_item.product_variant = mock_variant

        mock_order_items.return_value = [mock_item]

        mock_storage_save.return_value = 'exports/test.csv'

        mock_storage_url.return_value = (
            '/media/exports/test.csv'
        )

        result = export_vendor_orders_csv.run(
            self.vendor.id,
            self.user.id,
        )

        self.assertEqual(result['status'], 'success')

        self.assertEqual(
            result['download_url'],
            '/media/exports/test.csv',
        )

        self.assertEqual(result['row_count'], 1)

        mock_storage_save.assert_called_once()
        mock_storage_url.assert_called_once()

    @patch('vendor.tasks.export_vendor_orders_csv.delay')
    def test_export_endpoint_returns_task_id_when_format_is_csv(
        self,
        mock_delay,
    ):
        mock_task = Mock()
        mock_task.id = 'task-456'

        mock_delay.return_value = mock_task

        response = self.client.get(
            '/api/v1/vendor/orders/export/?format=csv'
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_202_ACCEPTED,
        )

        self.assertEqual(
            response.data['task_id'],
            'task-456',
        )

        self.assertEqual(response.data['status'], 'queued')

        mock_delay.assert_called_once_with(
            self.vendor.id,
            self.user.id,
        )

    def test_export_endpoint_rejects_unsupported_format(self):
        response = self.client.get(
            '/api/v1/vendor/orders/export/?format=xlsx'
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        response = self.client.get(
            '/api/v1/vendor/orders/export/?format=json'
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_export_endpoint_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(
            '/api/v1/vendor/orders/export/?format=csv'
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class VendorOrderExportHelperFunctionsTests(TestCase):
    def test_count_order_items_handles_queryset_and_list(self):
        from vendor.tasks import count_order_items

        mock_list = [1, 2, 3, 4]

        self.assertEqual(
            count_order_items(mock_list),
            4,
        )

        mock_queryset = Mock()
        mock_queryset.count.return_value = 5

        self.assertEqual(
            count_order_items(mock_queryset),
            5,
        )

        self.assertEqual(count_order_items([]), 0)

    def test_get_order_customer_name_returns_full_name(self):
        from vendor.tasks import get_order_customer_name

        mock_order = Mock()

        mock_order.first_name = 'John'
        mock_order.last_name = 'Doe'

        result = get_order_customer_name(mock_order)

        self.assertEqual(result, 'John Doe')

    def test_get_order_customer_name_falls_back_to_customer_name(
        self,
    ):
        from vendor.tasks import get_order_customer_name

        mock_order = Mock()

        mock_order.first_name = ''
        mock_order.last_name = ''
        mock_order.customer_name = 'Jane Smith'

        result = get_order_customer_name(mock_order)

        self.assertEqual(result, 'Jane Smith')

    def test_get_order_customer_name_returns_empty_string_when_no_name(
        self,
    ):
        from vendor.tasks import get_order_customer_name

        mock_order = Mock()

        mock_order.first_name = ''
        mock_order.last_name = ''
        mock_order.customer_name = ''

        result = get_order_customer_name(mock_order)

        self.assertEqual(result, '')

    def test_get_order_item_product_name_from_product_variant(
        self,
    ):
        from vendor.tasks import get_order_item_product_name

        mock_product = Mock()
        mock_product.name = 'MacBook Pro'

        mock_variant = Mock()
        mock_variant.product = mock_product

        mock_item = Mock()
        mock_item.product_variant = mock_variant

        result = get_order_item_product_name(mock_item)

        self.assertEqual(result, 'MacBook Pro')

    def test_get_order_item_product_name_from_variant(self):
        from vendor.tasks import get_order_item_product_name

        mock_product = Mock()
        mock_product.name = 'iPhone 15'

        mock_variant = Mock()
        mock_variant.product = mock_product

        mock_item = Mock()

        mock_item.variant = mock_variant
        mock_item.product_variant = None

        result = get_order_item_product_name(mock_item)

        self.assertEqual(result, 'iPhone 15')

    def test_get_order_item_product_name_from_product(self):
        from vendor.tasks import get_order_item_product_name

        mock_product = Mock()
        mock_product.name = 'iPad Air'

        mock_item = Mock()

        mock_item.product = mock_product
        mock_item.product_variant = None
        mock_item.variant = None

        result = get_order_item_product_name(mock_item)

        self.assertEqual(result, 'iPad Air')

    def test_get_order_item_product_name_returns_empty_when_no_product(
        self,
    ):
        from vendor.tasks import get_order_item_product_name

        mock_item = Mock()

        mock_item.product_variant = None
        mock_item.variant = None
        mock_item.product = None

        result = get_order_item_product_name(mock_item)

        self.assertEqual(result, '')

    def test_get_order_item_unit_price_from_price(self):
        from vendor.tasks import get_order_item_unit_price

        mock_item = Mock()
        mock_item.price = '99.99'

        result = get_order_item_unit_price(mock_item)

        self.assertEqual(result, '99.99')

    def test_get_order_item_unit_price_from_unit_price(self):
        from vendor.tasks import get_order_item_unit_price

        mock_item = Mock()

        mock_item.price = None
        mock_item.unit_price = '49.99'

        result = get_order_item_unit_price(mock_item)

        self.assertEqual(result, '49.99')

    def test_get_order_item_unit_price_returns_empty_when_no_price(
        self,
    ):
        from vendor.tasks import get_order_item_unit_price

        mock_item = Mock()

        mock_item.price = None
        mock_item.unit_price = None

        result = get_order_item_unit_price(mock_item)

        self.assertEqual(result, '')
