from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from tenants.models import Tenant


User = get_user_model()


class JwtClaimsTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store',
            domain='acme.example.com',
            plan='basic',
        )
        self.user = User.objects.create_user(
            email='admin@example.com',
            password='StrongPass123',
            first_name='Vendor',
            last_name='Admin',
            role='vendor_admin',
            tenant=self.tenant,
        )

    def test_login_token_contains_role_and_tenant_id_claims(self):
        response = self.client.post(
            reverse('login'),
            {
                'email': 'admin@example.com',
                'password': 'StrongPass123',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        access_token = AccessToken(response.data['access'])
        refresh_token = RefreshToken(response.data['refresh'])
        self.assertEqual(access_token['role'], 'vendor_admin')
        self.assertEqual(access_token['tenant_id'], self.tenant.id)
        self.assertEqual(refresh_token['role'], 'vendor_admin')
        self.assertEqual(refresh_token['tenant_id'], self.tenant.id)

    def test_refreshed_access_token_preserves_role_and_tenant_id_claims(self):
        login_response = self.client.post(
            reverse('login'),
            {
                'email': 'admin@example.com',
                'password': 'StrongPass123',
            },
            format='json',
        )

        refresh_response = self.client.post(
            reverse('token_refresh'),
            {'refresh': login_response.data['refresh']},
            format='json',
        )

        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        access_token = AccessToken(refresh_response.data['access'])
        self.assertEqual(access_token['role'], 'vendor_admin')
        self.assertEqual(access_token['tenant_id'], self.tenant.id)

    def test_registration_token_contains_default_role_and_null_tenant_id_claims(self):
        response = self.client.post(
            reverse('register'),
            {
                'email': 'customer@example.com',
                'first_name': 'Customer',
                'last_name': 'User',
                'password': 'StrongPass123',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        access_token = AccessToken(response.data['access'])
        refresh_token = RefreshToken(response.data['refresh'])
        self.assertEqual(access_token['role'], 'customer')
        self.assertIsNone(access_token['tenant_id'])
        self.assertEqual(refresh_token['role'], 'customer')
        self.assertIsNone(refresh_token['tenant_id'])
