from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
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


class RoleGroupAssignmentTests(APITestCase):
    def test_user_is_auto_assigned_group_matching_role_on_creation(self):
        roles = [
            'vendor_admin',
            'store_staff',
            'customer',
        ]

        for role in roles:
            with self.subTest(role=role):
                user = User.objects.create_user(
                    email=f'{role}@example.com',
                    password='StrongPass123',
                    first_name='Role',
                    last_name='User',
                    role=role,
                )

                self.assertTrue(user.groups.filter(name=role).exists())

    def test_superadmin_is_not_assigned_managed_role_group(self):
        user = User.objects.create_superuser(
            email='superadmin@example.com',
            password='StrongPass123',
            first_name='Super',
            last_name='Admin',
        )

        self.assertFalse(
            user.groups.filter(
                name__in=['vendor_admin', 'store_staff', 'customer']
            ).exists()
        )


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


class PasswordResetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='customer@example.com',
            password='OldStrongPass123',
            first_name='Customer',
            last_name='User',
            role='customer',
        )

    def test_password_reset_sends_email_task_for_existing_user(self):
        with patch('users.views.send_password_reset_email.delay') as delay:
            response = self.client.post(
                reverse('password-reset'),
                {'email': 'customer@example.com'},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        delay.assert_called_once()
        user_id, uid, token = delay.call_args.args
        self.assertEqual(user_id, self.user.id)
        self.assertEqual(
            uid,
            urlsafe_base64_encode(force_bytes(self.user.pk)),
        )
        self.assertTrue(default_token_generator.check_token(self.user, token))

    def test_password_reset_does_not_reveal_unknown_email(self):
        with patch('users.views.send_password_reset_email.delay') as delay:
            response = self.client.post(
                reverse('password-reset'),
                {'email': 'missing@example.com'},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        delay.assert_not_called()

    def test_password_reset_confirm_sets_new_password(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        response = self.client.post(
            reverse('password-reset-confirm'),
            {
                'uid': uid,
                'token': token,
                'new_password': 'NewStrongPass123',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewStrongPass123'))

    def test_password_reset_confirm_rejects_invalid_token(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))

        response = self.client.post(
            reverse('password-reset-confirm'),
            {
                'uid': uid,
                'token': 'invalid-token',
                'new_password': 'NewStrongPass123',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldStrongPass123'))

    def test_password_reset_token_cannot_be_reused_after_password_change(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        first_response = self.client.post(
            reverse('password-reset-confirm'),
            {
                'uid': uid,
                'token': token,
                'new_password': 'NewStrongPass123',
            },
            format='json',
        )
        second_response = self.client.post(
            reverse('password-reset-confirm'),
            {
                'uid': uid,
                'token': token,
                'new_password': 'AnotherStrongPass123',
            },
            format='json',
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            second_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )


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
