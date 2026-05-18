from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from catalog.models import Brand, Category, Product
from .cache import tenant_cache_key
from .middleware import _thread_locals
from .models import Tenant
from .serializers import TenantSerializer


User = get_user_model()


class TenantCacheKeyTests(APITestCase):
    def tearDown(self):
        if hasattr(_thread_locals, 'tenant'):
            delattr(_thread_locals, 'tenant')

    def test_tenant_cache_key_includes_current_tenant(self):
        first_tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store',
            domain='acme.example.com',
        )
        second_tenant = Tenant.objects.create(
            name='Beta Store',
            slug='beta-store',
            domain='beta.example.com',
        )

        _thread_locals.tenant = first_tenant
        first_key = tenant_cache_key('catalog:products', 'ecommerce', 1)

        _thread_locals.tenant = second_tenant
        second_key = tenant_cache_key('catalog:products', 'ecommerce', 1)

        self.assertEqual(
            first_key,
            f'ecommerce:tenant:{first_tenant.id}:v1:catalog:products',
        )
        self.assertEqual(
            second_key,
            f'ecommerce:tenant:{second_tenant.id}:v1:catalog:products',
        )
        self.assertNotEqual(first_key, second_key)

    def test_tenant_cache_key_uses_public_prefix_without_current_tenant(self):
        if hasattr(_thread_locals, 'tenant'):
            delattr(_thread_locals, 'tenant')

        cache_key = tenant_cache_key('catalog:products', 'ecommerce', 1)

        self.assertEqual(
            cache_key,
            'ecommerce:tenant:public:v1:catalog:products',
        )


class TenantDataIsolationTests(APITestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            name='Tenant A',
            slug='tenant-a',
            domain='tenant-a.example.com',
        )
        self.tenant_b = Tenant.objects.create(
            name='Tenant B',
            slug='tenant-b',
            domain='tenant-b.example.com',
        )

        self.brand_a = Brand.all_objects.create(
            tenant=self.tenant_a,
            name='Tenant A Brand',
            slug='tenant-a-brand',
        )
        self.brand_b = Brand.all_objects.create(
            tenant=self.tenant_b,
            name='Tenant B Brand',
            slug='tenant-b-brand',
        )
        self.category_a = Category.all_objects.create(
            tenant=self.tenant_a,
            name='Tenant A Laptops',
            slug='tenant-a-laptops',
        )
        self.category_b = Category.all_objects.create(
            tenant=self.tenant_b,
            name='Tenant B Laptops',
            slug='tenant-b-laptops',
        )
        self.product_a = Product.all_objects.create(
            tenant=self.tenant_a,
            name='Tenant A Laptop',
            slug='shared-laptop',
            sku='TENANT-A-LAPTOP',
            brand=self.brand_a,
            category=self.category_a,
            status=Product.Status.ACTIVE,
            base_price='999.00',
        )
        self.product_b = Product.all_objects.create(
            tenant=self.tenant_b,
            name='Tenant B Laptop',
            slug='shared-laptop',
            sku='TENANT-B-LAPTOP',
            brand=self.brand_b,
            category=self.category_b,
            status=Product.Status.ACTIVE,
            base_price='1299.00',
        )

    def tearDown(self):
        if hasattr(_thread_locals, 'tenant'):
            delattr(_thread_locals, 'tenant')

    def test_tenant_a_product_queries_do_not_return_tenant_b_data(self):
        _thread_locals.tenant = self.tenant_a

        visible_products = list(Product.objects.order_by('id'))

        self.assertEqual(visible_products, [self.product_a])
        self.assertNotIn(self.product_b, visible_products)

    def test_tenant_a_category_queries_do_not_return_tenant_b_data(self):
        _thread_locals.tenant = self.tenant_a

        visible_categories = list(Category.objects.order_by('id'))

        self.assertEqual(visible_categories, [self.category_a])
        self.assertNotIn(self.category_b, visible_categories)

    def test_same_slug_lookup_is_scoped_to_current_tenant(self):
        _thread_locals.tenant = self.tenant_a

        product = Product.objects.get(slug='shared-laptop')

        self.assertEqual(product, self.product_a)
        self.assertNotEqual(product, self.product_b)

    def test_tenant_b_data_exists_but_is_hidden_from_tenant_a_manager(self):
        _thread_locals.tenant = self.tenant_a

        self.assertEqual(
            Product.all_objects.filter(slug='shared-laptop').count(),
            2,
        )
        self.assertFalse(
            Product.objects.filter(sku=self.product_b.sku).exists()
        )


class TenantSerializerValidationTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store',
            domain='acme.example.com',
            plan='basic',
        )

    def test_duplicate_slug_is_rejected(self):
        serializer = TenantSerializer(
            data={
                'name': 'Duplicate Slug Store',
                'slug': 'acme-store',
                'domain': 'duplicate.example.com',
                'plan': 'free',
            },
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('slug', serializer.errors)

    def test_invalid_domain_format_is_rejected(self):
        serializer = TenantSerializer(
            data={
                'name': 'Invalid Domain Store',
                'slug': 'invalid-domain-store',
                'domain': 'not a domain',
                'plan': 'free',
            },
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('domain', serializer.errors)

    def test_domain_is_normalized_before_save(self):
        serializer = TenantSerializer(
            data={
                'name': 'Beta Store',
                'slug': 'beta-store',
                'domain': '  BETA.EXAMPLE.COM  ',
                'plan': 'premium',
            },
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        tenant = serializer.save()

        self.assertEqual(tenant.domain, 'beta.example.com')

    def test_existing_tenant_can_keep_own_slug_and_domain_on_update(self):
        serializer = TenantSerializer(
            self.tenant,
            data={
                'name': 'Acme Store Updated',
                'slug': 'acme-store',
                'domain': 'acme.example.com',
                'plan': 'premium',
                'is_active': True,
            },
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)


class TenantRegistrationTests(APITestCase):
    def setUp(self):
        self.url = reverse('tenant-register')
        self.payload = {
            'name': 'Acme Store',
            'slug': 'acme-store',
            'domain': 'shop.acme.com',
            'plan': 'basic',
            'email': 'owner@acme.com',
            'first_name': 'Acme',
            'last_name': 'Owner',
            'password': 'StrongPass123',
            'phone': '+123456789',
        }

    def test_vendor_can_register_tenant_and_vendor_admin(self):
        response = self.client.post(self.url, self.payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        tenant = Tenant.objects.get(slug='acme-store')
        user = User.objects.get(email='owner@acme.com')
        self.assertEqual(user.role, 'vendor_admin')
        self.assertEqual(user.tenant, tenant)
        self.assertEqual(tenant.owner, user)
        self.assertEqual(response.data['tenant']['id'], tenant.id)
        self.assertEqual(response.data['user']['id'], user.id)

        access_token = AccessToken(response.data['access'])
        self.assertEqual(access_token['role'], 'vendor_admin')
        self.assertEqual(access_token['tenant_id'], tenant.id)

    def test_duplicate_slug_is_rejected(self):
        Tenant.objects.create(
            name='Existing Store',
            slug='acme-store',
            domain='existing.example.com',
        )

        response = self.client.post(self.url, self.payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('slug', response.data)
        self.assertEqual(User.objects.count(), 0)

    def test_invalid_domain_is_rejected(self):
        payload = {
            **self.payload,
            'slug': 'invalid-domain-store',
            'domain': 'not a domain',
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('domain', response.data)
        self.assertFalse(
            Tenant.objects.filter(slug='invalid-domain-store').exists()
        )

    def test_tenant_creation_rolls_back_when_vendor_admin_creation_fails(self):
        with patch.object(
            User.objects,
            'create_user',
            side_effect=Exception('User creation failed'),
        ):
            with self.assertRaises(Exception):
                self.client.post(self.url, self.payload, format='json')

        self.assertFalse(Tenant.objects.filter(slug='acme-store').exists())

    def test_tenant_and_vendor_admin_roll_back_when_owner_assignment_fails(self):
        original_save = Tenant.save

        def fail_owner_assignment(instance, *args, **kwargs):
            if kwargs.get('update_fields') == ['owner']:
                raise Exception('Owner assignment failed')
            return original_save(instance, *args, **kwargs)

        with patch.object(Tenant, 'save', fail_owner_assignment):
            with self.assertRaises(Exception):
                self.client.post(self.url, self.payload, format='json')

        self.assertFalse(Tenant.objects.filter(slug='acme-store').exists())
        self.assertFalse(User.objects.filter(email='owner@acme.com').exists())
