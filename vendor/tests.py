from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, Mock
from .models import VendorProfile
from tenants.models import Tenant

User = get_user_model()

class VendorOrderSummaryTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Krijo tenant - pa schema_name sepse nuk ekziston
        self.tenant = Tenant.objects.create(
            name='Test Tenant'
            # schema_name nuk ekziston në modelin Tenant
        )
        
        # Krijo user vendor - përdor email si username
        self.user = User.objects.create_user(
            email='vendor@test.com',
            password='testpass123'
        )
        
        # Krijo vendor profile
        self.vendor = VendorProfile.objects.create(
            user=self.user,
            tenant=self.tenant,
            store_name='Test Store',
            contact_email='store@test.com'
        )
        
        self.client.force_authenticate(user=self.user)
    
    def test_order_summary_requires_auth(self):
        """Test that unauthenticated requests are rejected"""
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v1/vendor/orders/summary/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_order_summary_returns_200_for_vendor(self):
        """Test that authenticated vendor can access summary"""
        response = self.client.get('/api/v1/vendor/orders/summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_order_summary_returns_list(self):
        """Test that summary returns a list"""
        response = self.client.get('/api/v1/vendor/orders/summary/')
        self.assertIsInstance(response.data, list)
    
    def test_non_vendor_user_gets_404(self):
        """Test that non-vendor users get 404"""
        normal_user = User.objects.create_user(
            email='normal@test.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=normal_user)
        response = self.client.get('/api/v1/vendor/orders/summary/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class VendorOrdersExportTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Krijo tenant
        self.tenant = Tenant.objects.create(
            name='Test Tenant'
        )
        
        # Krijo user vendor
        self.user = User.objects.create_user(
            email='vendor2@test.com',
            password='testpass123'
        )
        
        # Krijo vendor profile
        self.vendor = VendorProfile.objects.create(
            user=self.user,
            tenant=self.tenant,
            store_name='Test Store 2',
            contact_email='store2@test.com'
        )
        
        self.client.force_authenticate(user=self.user)
    
    def test_export_csv_requires_auth(self):
        """Test that export endpoint requires authentication"""
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v1/vendor/orders/export/?format=csv')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    @patch('vendor.views.export_vendor_orders_csv')
    def test_export_csv_queues_task(self, mock_export_task):
        """Test that export endpoint queues a Celery task"""
        # Mock the Celery task
        mock_task = Mock()
        mock_task.id = 'test-task-id-123'
        mock_export_task.delay.return_value = mock_task
        
        response = self.client.get('/api/v1/vendor/orders/export/?format=csv')
        
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn('task_id', response.data)
        self.assertIn('status', response.data)
        self.assertEqual(response.data['status'], 'queued')
    
    def test_export_csv_requires_csv_format(self):
        """Test that export only accepts CSV format"""
        response = self.client.get('/api/v1/vendor/orders/export/?format=pdf')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_non_vendor_user_export_gets_404(self):
        """Test that non-vendor users get 404 on export"""
        normal_user = User.objects.create_user(
            email='normal2@test.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=normal_user)
        response = self.client.get('/api/v1/vendor/orders/export/?format=csv')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class VendorProfileModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Test Tenant'
        )
        self.user = User.objects.create_user(
            email='test@vendor.com',
            password='testpass'
        )
    
    def test_create_vendor_profile(self):
        """Test creating a vendor profile"""
        vendor = VendorProfile.objects.create(
            user=self.user,
            tenant=self.tenant,
            store_name='My Store',
            contact_email='contact@mystore.com'
        )
        
        self.assertEqual(vendor.store_name, 'My Store')
        self.assertEqual(vendor.contact_email, 'contact@mystore.com')
        self.assertTrue(vendor.is_active)
        self.assertEqual(vendor.rating, 0.0)
        self.assertEqual(vendor.total_sales, 0)
    
    def test_vendor_profile_str_method(self):
        """Test the string representation"""
        vendor = VendorProfile.objects.create(
            user=self.user,
            tenant=self.tenant,
            store_name='My Store',
            contact_email='contact@mystore.com'
        )
        
        expected_str = f"{vendor.store_name} - {self.tenant.name}"
        self.assertEqual(str(vendor), expected_str)
    
    def test_vendor_profile_unique_constraint(self):
        """Test that user and tenant combination must be unique"""
        VendorProfile.objects.create(
            user=self.user,
            tenant=self.tenant,
            store_name='Store 1',
            contact_email='store1@test.com'
        )
        
        # Try to create another vendor with same user and tenant
        with self.assertRaises(Exception):
            VendorProfile.objects.create(
                user=self.user,
                tenant=self.tenant,
                store_name='Store 2',
                contact_email='store2@test.com'
            )


class ExportStatusViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='vendor3@test.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_export_status_requires_task_id(self):
        """Test that status endpoint requires task_id parameter"""
        response = self.client.get('/api/v1/vendor/export/status/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_export_status_requires_auth(self):
        """Test that status endpoint requires authentication"""
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v1/vendor/export/status/?task_id=123')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class VendorURLsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name='Test Tenant')
        self.user = User.objects.create_user(
            email='vendor@test.com',
            password='testpass123'
        )
        self.vendor = VendorProfile.objects.create(
            user=self.user,
            tenant=self.tenant,
            store_name='Test Store',
            contact_email='store@test.com'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_order_summary_url_resolves(self):
        """Test that order summary URL resolves correctly"""
        response = self.client.get('/api/v1/vendor/orders/summary/')
        self.assertNotEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_export_url_resolves(self):
        """Test that export URL resolves correctly"""
        response = self.client.get('/api/v1/vendor/orders/export/?format=csv')
        self.assertNotEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_status_url_resolves(self):
        """Test that status URL resolves correctly"""
        response = self.client.get('/api/v1/vendor/export/status/?task_id=123')
        self.assertNotEqual(response.status_code, status.HTTP_404_NOT_FOUND)