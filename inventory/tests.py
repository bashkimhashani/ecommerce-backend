from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from catalog.models import Brand, Category, Product, ProductVariant
from tenants.models import Tenant
from vendor.models import VendorProfile
from .models import Inventory
from .tasks import send_low_stock_alert

User = get_user_model()


class InventoryAlertTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Test Tenant',
            slug='inventory-alerts',
            domain='inventory-alerts.local',
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
            contact_email='alerts@test.com',
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
            name='MacBook Pro',
            slug='macbook-pro',
            sku='MBP-001',
            brand=self.brand,
            category=self.category,
            status=Product.Status.ACTIVE,
            base_price='1999.00',
        )
        self.variant = ProductVariant.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            color='Space Black',
            storage='1TB',
            ram='32GB',
            variant_price='2499.00',
            stock_quantity=10,
        )

    def create_inventory(self, quantity=10, threshold=5):
        return Inventory.all_objects.create(
            tenant=self.tenant,
            vendor=self.vendor,
            product_variant=self.variant,
            quantity=quantity,
            low_stock_threshold=threshold,
        )

    @patch('inventory.signals.send_low_stock_alert.delay')
    def test_alert_queues_when_quantity_drops_below_threshold(self, mock_delay):
        inventory = self.create_inventory(quantity=5, threshold=5)

        inventory.quantity = 4
        inventory.save()

        mock_delay.assert_called_once_with(inventory.id)

    @patch('inventory.signals.send_low_stock_alert.delay')
    def test_alert_does_not_queue_at_threshold_boundary(self, mock_delay):
        inventory = self.create_inventory(quantity=6, threshold=5)

        inventory.quantity = 5
        inventory.save()

        mock_delay.assert_not_called()

    @patch('inventory.signals.send_low_stock_alert.delay')
    def test_alert_does_not_queue_above_threshold(self, mock_delay):
        inventory = self.create_inventory(quantity=10, threshold=5)

        inventory.quantity = 6
        inventory.save()

        mock_delay.assert_not_called()

    @patch('inventory.signals.send_low_stock_alert.delay')
    def test_alert_does_not_repeat_while_already_below_threshold(self, mock_delay):
        inventory = self.create_inventory(quantity=4, threshold=5)

        inventory.quantity = 3
        inventory.save()

        mock_delay.assert_not_called()

    @patch('inventory.tasks.send_mail')
    def test_low_stock_task_sends_vendor_email(self, mock_send_mail):
        inventory = self.create_inventory(quantity=3, threshold=5)

        result = send_low_stock_alert(inventory.id)

        self.assertEqual(result['status'], 'sent')
        mock_send_mail.assert_called_once()
        call_kwargs = mock_send_mail.call_args.kwargs
        self.assertIn('Low stock alert', call_kwargs['subject'])
        self.assertEqual(
            call_kwargs['recipient_list'],
            ['alerts@test.com', 'vendor@test.com'],
        )
