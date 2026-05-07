from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from .models import Tenant


User = get_user_model()


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
