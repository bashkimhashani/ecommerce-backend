from io import BytesIO
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from tenants.models import Tenant
from .token_blacklist import get_token_blacklist_key


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


class FakeRedisConnection:
    def __init__(self):
        self.setex_calls = []
        self.existing_keys = set()

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.existing_keys.add(key)

    def exists(self, key):
        return key in self.existing_keys


class LogoutRedisBlacklistTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='customer@example.com',
            password='StrongPass123',
            first_name='Customer',
            last_name='User',
            role='customer',
        )

    def test_logout_stores_refresh_and_access_tokens_in_redis_with_ttl(self):
        redis_connection = FakeRedisConnection()
        refresh = RefreshToken.for_user(self.user)
        access = refresh.access_token

        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {str(access)}',
        )

        with patch(
            'users.token_blacklist.get_redis_connection',
            return_value=redis_connection,
        ):
            response = self.client.post(
                reverse('logout'),
                {'refresh': str(refresh)},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        blacklist_keys = {call[0] for call in redis_connection.setex_calls}
        self.assertEqual(
            blacklist_keys,
            {
                get_token_blacklist_key(refresh['jti']),
                get_token_blacklist_key(access['jti']),
            },
        )
        for _, ttl, value in redis_connection.setex_calls:
            self.assertGreater(ttl, 0)
            self.assertEqual(value, '1')

    def test_redis_blacklisted_access_token_is_rejected(self):
        redis_connection = FakeRedisConnection()
        access = RefreshToken.for_user(self.user).access_token
        redis_connection.existing_keys.add(get_token_blacklist_key(access['jti']))

        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {str(access)}',
        )

        with patch(
            'users.token_blacklist.get_redis_connection',
            return_value=redis_connection,
        ):
            response = self.client.get(reverse('me'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


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
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
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

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)
        super().tearDown()

    def image_upload(self, name='avatar.jpg', size=(900, 700)):
        image = Image.new('RGB', size, color='white')
        output = BytesIO()
        image.save(output, format='JPEG')
        output.seek(0)
        return SimpleUploadedFile(
            name,
            output.read(),
            content_type='image/jpeg',
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

    def test_user_can_upload_avatar_and_thumbnail_is_generated(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse('user-me'),
            {'avatar': self.image_upload()},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar.name)
        self.assertTrue(self.user.avatar_thumbnail.name)
        self.assertTrue(self.user.avatar.storage.exists(
            self.user.avatar.name,
        ))
        self.assertTrue(self.user.avatar_thumbnail.storage.exists(
            self.user.avatar_thumbnail.name,
        ))
        self.assertIn('avatar', response.data)
        self.assertIn('avatar_thumbnail', response.data)

        self.user.avatar_thumbnail.open('rb')
        thumbnail = Image.open(self.user.avatar_thumbnail)
        thumbnail.load()
        self.user.avatar_thumbnail.close()

        self.assertLessEqual(thumbnail.width, 256)
        self.assertLessEqual(thumbnail.height, 256)
        self.assertEqual(thumbnail.format, 'JPEG')

    def test_avatar_upload_rejects_non_image_file(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse('user-me'),
            {
                'avatar': SimpleUploadedFile(
                    'avatar.txt',
                    b'not an image',
                    content_type='text/plain',
                ),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('avatar', response.data)

    def test_profile_patch_requires_authentication(self):
        response = self.client.patch(
            reverse('user-me'),
            {'first_name': 'Updated'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
