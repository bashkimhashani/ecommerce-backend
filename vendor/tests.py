from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import Mock, patch

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
        self.assertEqual(response.data['low_stock_items'][0]['id'], self.inventory.id)

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
        self.assertEqual(response.data[0]['variant_name'], 'Silver / 512GB / 16GB')
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
    def test_order_summary_endpoint_returns_grouped_status_counts(self, mock_summary):
        cache.clear()
        mock_summary.return_value = [
            {'status': 'paid', 'count': 2, 'total_amount': '250.00'},
            {'status': 'shipped', 'count': 1, 'total_amount': '80.00'},
        ]

        response = self.client.get('/api/v1/vendor/orders/summary/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['status'], 'paid')
        self.assertEqual(response.data[0]['count'], 2)
        self.assertEqual(str(response.data[0]['total_amount']), '250.00')
        mock_summary.assert_called_once_with(self.vendor)

    @patch('vendor.tasks.export_vendor_orders_csv.delay')
    def test_orders_export_queues_csv_task(self, mock_delay):
        mock_task = Mock()
        mock_task.id = 'export-task-123'
        mock_delay.return_value = mock_task

        response = self.client.get('/api/v1/vendor/orders/export/?format=csv')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['task_id'], 'export-task-123')
        self.assertEqual(response.data['status'], 'queued')
        mock_delay.assert_called_once_with(self.vendor.id, self.user.id)

    def test_orders_export_rejects_non_csv_format(self):
        response = self.client.get('/api/v1/vendor/orders/export/?format=pdf')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


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
    def test_summary_helper_groups_by_order_status_for_vendor_items(self, mock_model):
        FakeOrderItemModel.objects = FakeOrderItemManager()
        mock_model.return_value = FakeOrderItemModel

        rows = vendor_order_summary_rows(self.vendor)

        self.assertEqual(rows, [
            {'status': 'paid', 'count': 2, 'total_amount': '250'},
            {'status': 'shipped', 'count': 1, 'total_amount': '80'},
        ])
        self.assertEqual(
            FakeOrderItemModel.objects.filter_kwargs,
            {
                'order__tenant': self.tenant,
                'product_variant__inventory_items__vendor': self.vendor,
            },
        )
        queryset = FakeOrderItemModel.objects.queryset
        self.assertEqual(queryset.select_related_args, ('order',))
        self.assertEqual(queryset.summary_values.values_args, ('order__status',))
        self.assertEqual(queryset.summary_values.order_by_args, ('order__status',))
