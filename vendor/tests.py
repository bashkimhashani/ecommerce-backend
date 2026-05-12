from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from catalog.models import Brand, Category, Product, ProductVariant
from inventory.models import Inventory
from tenants.models import Tenant
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
