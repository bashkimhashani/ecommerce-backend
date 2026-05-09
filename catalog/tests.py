from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from tenants.models import Tenant

from .models import Category


User = get_user_model()


class CategoryTreeEndpointTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store',
            domain='acme.example.com',
            plan='basic',
        )
        self.user = User.objects.create_user(
            email='vendor@example.com',
            password='StrongPass123',
            first_name='Vendor',
            last_name='Admin',
            role='vendor_admin',
            tenant=self.tenant,
        )
        self.url = reverse('category-tree')

    def test_category_tree_returns_nested_active_categories(self):
        laptops = Category.all_objects.create(
            tenant=self.tenant,
            name='Laptops',
            slug='laptops',
            icon_url='https://example.com/icons/laptops.svg',
        )
        ultrabooks = Category.all_objects.create(
            tenant=self.tenant,
            parent=laptops,
            name='Ultrabooks',
            slug='ultrabooks',
        )
        Category.all_objects.create(
            tenant=self.tenant,
            parent=ultrabooks,
            name='Business Ultrabooks',
            slug='business-ultrabooks',
        )
        Category.all_objects.create(
            tenant=self.tenant,
            parent=laptops,
            name='Inactive Gaming',
            slug='inactive-gaming',
            is_active=False,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['slug'], 'laptops')
        self.assertEqual(response.data[0]['icon_url'], laptops.icon_url)
        self.assertEqual(len(response.data[0]['children']), 1)
        self.assertEqual(response.data[0]['children'][0]['slug'], 'ultrabooks')
        self.assertEqual(
            response.data[0]['children'][0]['children'][0]['slug'],
            'business-ultrabooks',
        )

    def test_category_tree_excludes_other_tenants_for_authenticated_user(self):
        other_tenant = Tenant.objects.create(
            name='Other Store',
            slug='other-store',
            domain='other.example.com',
            plan='basic',
        )
        Category.all_objects.create(
            tenant=self.tenant,
            name='Accessories',
            slug='accessories',
        )
        Category.all_objects.create(
            tenant=other_tenant,
            name='Other Accessories',
            slug='other-accessories',
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [category['slug'] for category in response.data],
            ['accessories'],
        )
