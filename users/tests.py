from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from tenants.models import Tenant


User = get_user_model()


class RoleGroupMigrationTests(APITestCase):
    def test_role_groups_exist_after_migrations(self):
        expected_groups = {
            'vendor_admin',
            'store_staff',
            'customer',
        }

        existing_groups = set(
            Group.objects.filter(name__in=expected_groups).values_list(
                'name',
                flat=True,
            )
        )

        self.assertEqual(existing_groups, expected_groups)


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


class UserProfileTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store',
            domain='acme.example.com',
            plan='basic',
        )
        self.other_tenant = Tenant.objects.create(
            name='Other Store',
            slug='other-store',
            domain='other.example.com',
            plan='premium',
        )
        self.user = User.objects.create_user(
            email='customer@example.com',
            password='StrongPass123',
            first_name='Customer',
            last_name='User',
            role='customer',
            tenant=self.tenant,
        )

    def test_user_can_patch_own_profile(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse('user-me'),
            {
                'first_name': 'Updated',
                'last_name': 'Customer',
                'phone': '+36301234567',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.user.last_name, 'Customer')
        self.assertEqual(self.user.phone, '+36301234567')
        self.assertEqual(response.data['first_name'], 'Updated')

    def test_profile_patch_does_not_update_role_or_tenant(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse('user-me'),
            {
                'role': 'superadmin',
                'tenant': self.other_tenant.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, 'customer')
        self.assertEqual(self.user.tenant, self.tenant)
        self.assertEqual(response.data['role'], 'customer')
        self.assertEqual(response.data['tenant'], self.tenant.id)

    def test_auth_me_route_also_supports_patch(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse('me'),
            {'phone': '+36307654321'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, '+36307654321')

    def test_profile_patch_requires_authentication(self):
        response = self.client.patch(
            reverse('user-me'),
            {'first_name': 'Updated'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
