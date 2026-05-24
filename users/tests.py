from io import BytesIO
from datetime import timedelta
import shutil
import tempfile
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.test import SimpleTestCase
from django.urls import resolve, reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from PIL import Image
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from tenants.models import Tenant
from .token_blacklist import get_token_blacklist_key
from .tokens import email_verification_token_generator


User = get_user_model()


class AuthEndpointPermissionTests(SimpleTestCase):
    def assert_permission_classes(self, url_name, expected):
        view_class = resolve(reverse(url_name)).func.view_class
        self.assertEqual(view_class.permission_classes, expected)

    def test_public_auth_endpoints_have_explicit_permissions(self):
        public_endpoints = [
            'register',
            'email-verify',
            'login',
            'token_refresh',
            'password-reset',
            'password-reset-confirm',
        ]

        for url_name in public_endpoints:
            with self.subTest(url_name=url_name):
                self.assert_permission_classes(url_name, [AllowAny])

    def test_authenticated_auth_endpoints_have_explicit_permissions(self):
        protected_endpoints = [
            'logout',
            'me',
            'user-me',
        ]

        for url_name in protected_endpoints:
            with self.subTest(url_name=url_name):
                self.assert_permission_classes(url_name, [IsAuthenticated])


class RoleEndpointForbiddenMatrixTests(APITestCase):
    all_roles = ('superadmin', 'vendor_admin', 'store_staff', 'customer')
    role_endpoint_matrix = (
        {
            'name': 'checkout-session',
            'method': 'post',
            'url_name': 'checkout-session',
            'allowed_roles': ('customer',),
        },
        {
            'name': 'checkout-session-address',
            'method': 'patch',
            'url_name': 'checkout-session-address',
            'args': (1,),
            'allowed_roles': ('customer',),
        },
        {
            'name': 'checkout-session-payment-intent',
            'method': 'post',
            'url_name': 'checkout-session-payment-intent',
            'args': (1,),
            'allowed_roles': ('customer',),
        },
        {
            'name': 'customer-order-list',
            'method': 'get',
            'url_name': 'customer-order-list',
            'allowed_roles': ('customer',),
        },
        {
            'name': 'customer-order-detail',
            'method': 'get',
            'url_name': 'customer-order-detail',
            'args': ('ORD-123',),
            'allowed_roles': ('customer',),
        },
        {
            'name': 'customer-order-cancel',
            'method': 'post',
            'url_name': 'customer-order-cancel',
            'args': (1,),
            'allowed_roles': ('customer',),
        },
        {
            'name': 'product-list-create',
            'method': 'post',
            'url_name': 'product-list',
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'product-detail-update',
            'method': 'put',
            'url_name': 'product-detail',
            'args': ('sample-product',),
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'product-detail-delete',
            'method': 'delete',
            'url_name': 'product-detail',
            'args': ('sample-product',),
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'product-image-upload',
            'method': 'post',
            'url_name': 'product-image-upload',
            'args': ('sample-product',),
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'product-image-reorder',
            'method': 'patch',
            'url_name': 'product-image-upload',
            'args': ('sample-product',),
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'product-image-delete',
            'method': 'delete',
            'url_name': 'product-image-delete',
            'args': ('sample-product', 1),
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'vendor-dashboard-summary',
            'method': 'get',
            'url_name': 'vendor-dashboard-summary',
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'vendor-inventory-list',
            'method': 'get',
            'url_name': 'vendor-inventory-list',
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'vendor-inventory-detail',
            'method': 'patch',
            'url_name': 'vendor-inventory-detail',
            'args': (1,),
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'vendor-order-summary',
            'method': 'get',
            'url_name': 'vendor-order-summary',
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'vendor-order-export',
            'method': 'get',
            'url_name': 'vendor-order-export',
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'vendor-export-status',
            'method': 'get',
            'url_name': 'export-status',
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'vendor-order-list',
            'method': 'get',
            'url_name': 'vendor-order-list',
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'vendor-order-confirm',
            'method': 'post',
            'url_name': 'vendor-order-confirm',
            'args': (1,),
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'vendor-order-mark-shipped',
            'method': 'post',
            'url_name': 'vendor-order-mark-shipped',
            'args': (1,),
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'vendor-order-mark-delivered',
            'method': 'post',
            'url_name': 'vendor-order-mark-delivered',
            'args': (1,),
            'allowed_roles': ('vendor_admin',),
        },
        {
            'name': 'admin-request-log-list',
            'method': 'get',
            'url_name': 'admin-request-log-list',
            'allowed_roles': ('superadmin',),
        },
    )

    def setUp(self):
        self.users_by_role = {
            'superadmin': User.objects.create_superuser(
                email='superadmin@example.com',
                password='StrongPass123',
                first_name='Super',
                last_name='Admin',
            ),
            'vendor_admin': User.objects.create_user(
                email='vendor-admin@example.com',
                password='StrongPass123',
                first_name='Vendor',
                last_name='Admin',
                role='vendor_admin',
            ),
            'store_staff': User.objects.create_user(
                email='store-staff@example.com',
                password='StrongPass123',
                first_name='Store',
                last_name='Staff',
                role='store_staff',
            ),
            'customer': User.objects.create_user(
                email='customer-role@example.com',
                password='StrongPass123',
                first_name='Customer',
                last_name='User',
                role='customer',
            ),
        }

    def request_endpoint(self, endpoint):
        url = reverse(endpoint['url_name'], args=endpoint.get('args', ()))
        method = getattr(self.client, endpoint['method'])
        if endpoint['method'] in {'post', 'put', 'patch'}:
            return method(url, {}, format='json')
        return method(url)

    def test_disallowed_roles_receive_403_for_role_protected_endpoints(self):
        for endpoint in self.role_endpoint_matrix:
            disallowed_roles = (
                set(self.all_roles) - set(endpoint['allowed_roles'])
            )
            for role in sorted(disallowed_roles):
                with self.subTest(endpoint=endpoint['name'], role=role):
                    self.client.force_authenticate(
                        user=self.users_by_role[role],
                    )

                    response = self.request_endpoint(endpoint)

                    self.assertEqual(
                        response.status_code,
                        status.HTTP_403_FORBIDDEN,
                    )


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

                assigned_groups = set(user.groups.values_list('name', flat=True))
                self.assertEqual(assigned_groups, {role})

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


class AdminModulePermissionTests(APITestCase):
    def create_staff_user(self, role):
        return User.objects.create_user(
            email=f'{role}-admin@example.com',
            password='StrongPass123',
            first_name='Admin',
            last_name='User',
            role=role,
            is_staff=True,
        )

    def test_vendor_admin_group_can_access_vendor_operational_admin_modules(self):
        user = self.create_staff_user('vendor_admin')

        allowed_modules = ['catalog', 'inventory', 'vendor']
        blocked_modules = ['users', 'tenants', 'auth']

        for app_label in allowed_modules:
            with self.subTest(app_label=app_label):
                self.assertTrue(user.has_module_perms(app_label))

        for app_label in blocked_modules:
            with self.subTest(app_label=app_label):
                self.assertFalse(user.has_module_perms(app_label))

    def test_store_staff_group_can_access_store_operational_admin_modules(self):
        user = self.create_staff_user('store_staff')

        allowed_modules = ['catalog', 'inventory']
        blocked_modules = ['vendor', 'users', 'tenants', 'auth']

        for app_label in allowed_modules:
            with self.subTest(app_label=app_label):
                self.assertTrue(user.has_module_perms(app_label))

        for app_label in blocked_modules:
            with self.subTest(app_label=app_label):
                self.assertFalse(user.has_module_perms(app_label))

    def test_customer_group_cannot_access_admin_modules(self):
        user = self.create_staff_user('customer')

        for app_label in ['catalog', 'inventory', 'vendor', 'users', 'tenants']:
            with self.subTest(app_label=app_label):
                self.assertFalse(user.has_module_perms(app_label))

    def test_superadmin_can_access_all_admin_modules(self):
        user = User.objects.create_superuser(
            email='superadmin-admin@example.com',
            password='StrongPass123',
            first_name='Super',
            last_name='Admin',
        )

        for app_label in ['catalog', 'inventory', 'vendor', 'users', 'tenants']:
            with self.subTest(app_label=app_label):
                self.assertTrue(user.has_module_perms(app_label))

    def test_inactive_user_cannot_access_admin_modules(self):
        user = self.create_staff_user('vendor_admin')
        user.is_active = False
        user.save(update_fields=['is_active'])

        self.assertFalse(user.has_module_perms('catalog'))


class LoginEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='customer@example.com',
            password='StrongPass123',
            first_name='Customer',
            last_name='User',
            role='customer',
        )

    def test_login_success_returns_access_and_refresh_tokens(self):
        response = self.client.post(
            reverse('login'),
            {
                'email': 'customer@example.com',
                'password': 'StrongPass123',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(
            AccessToken(response.data['access'])['user_id'],
            str(self.user.id),
        )
        self.assertEqual(
            RefreshToken(response.data['refresh'])['user_id'],
            str(self.user.id),
        )

    def test_login_wrong_password_is_rejected(self):
        response = self.client.post(
            reverse('login'),
            {
                'email': 'customer@example.com',
                'password': 'WrongStrongPass123',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh', response.data)
        self.assertIn('detail', response.data)

    def test_expired_access_token_is_rejected(self):
        token = AccessToken.for_user(self.user)
        token.set_exp(lifetime=timedelta(seconds=-1))

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token)}')
        response = self.client.get(reverse('me'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'token_not_valid')

    def test_invalid_access_token_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer not-a-valid-token')

        response = self.client.get(reverse('me'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'token_not_valid')


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

    @patch('users.services.CartService.merge_carts')
    @patch('users.services.CartService.get_or_create_cart')
    @patch('users.services.Cart.objects')
    def test_login_merges_guest_cart_into_user_cart(
        self,
        cart_objects,
        get_or_create_cart,
        merge_carts,
    ):
        session = self.client.session
        session['cart_exists'] = True
        session.save()
        guest_cart = Mock()
        user_cart = Mock()
        cart_objects.filter.return_value.first.return_value = guest_cart
        get_or_create_cart.return_value = user_cart

        response = self.client.post(
            reverse('login'),
            {
                'email': 'admin@example.com',
                'password': 'StrongPass123',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cart_objects.filter.assert_called_once_with(
            session_key=session.session_key,
            status='active',
        )
        get_or_create_cart.assert_called_once()
        cart_request = get_or_create_cart.call_args.args[0]
        self.assertEqual(cart_request.user, self.user)
        self.assertEqual(cart_request.tenant, self.tenant)
        merge_carts.assert_called_once_with(guest_cart, user_cart)

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


class RegistrationEndpointTests(APITestCase):
    def register_payload(self, **overrides):
        payload = {
            'email': 'new-customer@example.com',
            'first_name': 'New',
            'last_name': 'Customer',
            'password': 'StrongPass123',
        }
        payload.update(overrides)
        return payload

    def test_registration_creates_unverified_user_and_sends_verification_email(self):
        with patch('users.services.send_email_verification_email.delay') as delay:
            response = self.client.post(
                reverse('register'),
                self.register_payload(),
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertNotIn('password', response.data['user'])
        self.assertEqual(response.data['user']['email'], 'new-customer@example.com')
        self.assertFalse(response.data['user']['is_email_verified'])

        user = User.objects.get(email='new-customer@example.com')
        self.assertEqual(user.first_name, 'New')
        self.assertEqual(user.last_name, 'Customer')
        self.assertEqual(user.role, 'customer')
        self.assertTrue(user.check_password('StrongPass123'))
        self.assertFalse(user.is_email_verified)

        delay.assert_called_once()
        user_id, uid, token = delay.call_args.args
        self.assertEqual(user_id, user.id)
        self.assertEqual(uid, urlsafe_base64_encode(force_bytes(user.pk)))
        self.assertTrue(
            email_verification_token_generator.check_token(user, token),
        )

    def test_registration_honors_valid_role(self):
        with patch('users.services.send_email_verification_email.delay'):
            response = self.client.post(
                reverse('register'),
                self.register_payload(
                    email='vendor@example.com',
                    role='vendor_admin',
                ),
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user']['role'], 'vendor_admin')
        self.assertTrue(
            User.objects.get(email='vendor@example.com')
            .groups.filter(name='vendor_admin')
            .exists(),
        )

    def test_registration_rejects_duplicate_email_without_sending_email(self):
        User.objects.create_user(
            email='new-customer@example.com',
            password='StrongPass123',
            first_name='Existing',
            last_name='Customer',
        )

        with patch('users.services.send_email_verification_email.delay') as delay:
            response = self.client.post(
                reverse('register'),
                self.register_payload(),
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)
        delay.assert_not_called()
        self.assertEqual(
            User.objects.filter(email='new-customer@example.com').count(),
            1,
        )

    def test_registration_rejects_invalid_payload_without_sending_email(self):
        with patch('users.services.send_email_verification_email.delay') as delay:
            response = self.client.post(
                reverse('register'),
                self.register_payload(email='not-an-email', password='short'),
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)
        self.assertIn('password', response.data)
        delay.assert_not_called()


class EmailVerificationEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='customer@example.com',
            password='StrongPass123',
            first_name='Customer',
            last_name='User',
            role='customer',
        )
        self.uid = urlsafe_base64_encode(force_bytes(self.user.pk))

    def verification_token(self):
        self.user.refresh_from_db()
        return email_verification_token_generator.make_token(self.user)

    def test_email_verification_marks_user_as_verified(self):
        token = self.verification_token()

        response = self.client.post(
            reverse('email-verify'),
            {'uid': self.uid, 'token': token},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)
        self.assertEqual(
            response.data['message'],
            'Email has been verified successfully.',
        )

    def test_email_verification_rejects_invalid_token(self):
        response = self.client.post(
            reverse('email-verify'),
            {'uid': self.uid, 'token': 'invalid-token'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_email_verified)

    def test_email_verification_rejects_invalid_uid(self):
        response = self.client.post(
            reverse('email-verify'),
            {'uid': 'not-a-valid-uid', 'token': self.verification_token()},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_email_verified)

    def test_email_verification_token_cannot_be_reused(self):
        token = self.verification_token()

        first_response = self.client.post(
            reverse('email-verify'),
            {'uid': self.uid, 'token': token},
            format='json',
        )
        second_response = self.client.post(
            reverse('email-verify'),
            {'uid': self.uid, 'token': token},
            format='json',
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)


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
        with patch('users.services.send_password_reset_email.delay') as delay:
            response = self.client.post(
                reverse('password-reset'),
                {'email': 'customer@example.com'},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        delay.assert_called_once()
        user_id, token = delay.call_args.args
        self.assertEqual(user_id, self.user.id)
        self.assertTrue(default_token_generator.check_token(self.user, token))

    def test_password_reset_does_not_reveal_unknown_email(self):
        with patch('users.services.send_password_reset_email.delay') as delay:
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

    def test_user_can_get_own_profile(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse('user-me'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.user.id)
        self.assertEqual(response.data['email'], 'customer@example.com')
        self.assertEqual(response.data['first_name'], 'Customer')
        self.assertEqual(response.data['last_name'], 'User')
        self.assertEqual(response.data['role'], 'customer')
        self.assertEqual(response.data['tenant'], self.tenant.id)
        self.assertIsNone(response.data['phone'])
        self.assertIn('avatar', response.data)
        self.assertIn('avatar_thumbnail', response.data)
        self.assertIn('date_joined', response.data)

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

    def test_profile_patch_does_not_update_email_or_date_joined(self):
        self.client.force_authenticate(user=self.user)
        original_date_joined = self.user.date_joined

        response = self.client.patch(
            reverse('user-me'),
            {
                'email': 'changed@example.com',
                'date_joined': '2000-01-01T00:00:00Z',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'customer@example.com')
        self.assertEqual(self.user.date_joined, original_date_joined)
        self.assertEqual(response.data['email'], 'customer@example.com')

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

    def test_profile_get_requires_authentication(self):
        response = self.client.get(reverse('user-me'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_patch_requires_authentication(self):
        response = self.client.patch(
            reverse('user-me'),
            {'first_name': 'Updated'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
