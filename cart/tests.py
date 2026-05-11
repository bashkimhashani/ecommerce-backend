from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from tenants.models import Tenant

from .cache import CART_CACHE_TTL_SECONDS, CartRedisCache
from .models import Cart
from .services import CartService


User = get_user_model()


class CartRedisCacheTests(APITestCase):
    def test_cart_cache_key_uses_session_key(self):
        self.assertEqual(
            CartRedisCache.key('guest-session-123'),
            'cart:guest-session-123',
        )

    @patch.object(CartRedisCache, 'get_client')
    @patch.object(CartRedisCache, 'serialize_cart')
    def test_store_cart_writes_serialized_cart_with_seven_day_ttl(
        self,
        serialize_cart,
        get_client,
    ):
        cart = SimpleNamespace(session_key='guest-session-123')
        redis_client = Mock()
        serialize_cart.return_value = {
            'id': 1,
            'items': [],
            'total_items': 0,
            'subtotal': '0.00',
        }
        get_client.return_value = redis_client

        payload = CartRedisCache.store_cart(cart)

        self.assertEqual(payload, serialize_cart.return_value)
        redis_client.setex.assert_called_once()
        key, ttl, serialized_payload = redis_client.setex.call_args.args
        self.assertEqual(key, 'cart:guest-session-123')
        self.assertEqual(ttl, CART_CACHE_TTL_SECONDS)
        self.assertIn('"items": []', serialized_payload)

    @patch.object(CartRedisCache, 'get_client')
    def test_store_cart_skips_carts_without_session_key(self, get_client):
        cart = SimpleNamespace(session_key=None)

        payload = CartRedisCache.store_cart(cart)

        self.assertIsNone(payload)
        get_client.assert_not_called()

    @patch.object(CartRedisCache, 'get_client')
    def test_get_cart_reads_serialized_cart_by_session_key(self, get_client):
        redis_client = Mock()
        redis_client.get.return_value = (
            '{"id": 1, "items": [], "total_items": 0, "subtotal": "0.00"}'
        )
        get_client.return_value = redis_client

        payload = CartRedisCache.get_cart('guest-session-123')

        redis_client.get.assert_called_once_with('cart:guest-session-123')
        self.assertEqual(payload['id'], 1)
        self.assertEqual(payload['items'], [])

    @patch.object(CartRedisCache, 'get_client')
    def test_get_cart_returns_none_on_cache_miss(self, get_client):
        redis_client = Mock()
        redis_client.get.return_value = None
        get_client.return_value = redis_client

        payload = CartRedisCache.get_cart('guest-session-123')

        redis_client.get.assert_called_once_with('cart:guest-session-123')
        self.assertIsNone(payload)

    @patch.object(CartRedisCache, 'get_client')
    def test_invalidate_cart_deletes_session_key(self, get_client):
        redis_client = Mock()
        redis_client.delete.return_value = 1
        get_client.return_value = redis_client

        deleted_count = CartRedisCache.invalidate_cart('guest-session-123')

        redis_client.delete.assert_called_once_with('cart:guest-session-123')
        self.assertEqual(deleted_count, 1)

    @patch.object(CartRedisCache, 'get_client')
    def test_invalidate_cart_skips_missing_session_key(self, get_client):
        deleted_count = CartRedisCache.invalidate_cart(None)

        self.assertEqual(deleted_count, 0)
        get_client.assert_not_called()


class CartServiceTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store',
            domain='acme.example.com',
            plan='basic',
        )
        self.user = User.objects.create_user(
            email='customer@example.com',
            password='StrongPass123',
            first_name='Customer',
            last_name='User',
            role='customer',
            tenant=self.tenant,
        )

    def test_get_or_create_cart_creates_authenticated_user_cart(self):
        request = SimpleNamespace(user=self.user, tenant=self.tenant)

        cart = CartService.get_or_create_cart(request)

        self.assertEqual(cart.user, self.user)
        self.assertIsNone(cart.session_key)
        self.assertEqual(cart.tenant, self.tenant)
        self.assertEqual(cart.status, Cart.Status.ACTIVE)

    def test_get_or_create_cart_reuses_authenticated_user_cart(self):
        request = SimpleNamespace(user=self.user, tenant=self.tenant)
        existing_cart = CartService.get_or_create_cart(request)

        cart = CartService.get_or_create_cart(request)

        self.assertEqual(cart, existing_cart)
        self.assertEqual(Cart.objects.filter(user=self.user).count(), 1)

    def test_get_or_create_cart_creates_guest_cart_with_session_key(self):
        request = SimpleNamespace(
            user=AnonymousUser(),
            tenant=self.tenant,
            session=SessionStore(),
        )

        cart = CartService.get_or_create_cart(request)

        self.assertIsNone(cart.user)
        self.assertEqual(cart.session_key, request.session.session_key)
        self.assertEqual(cart.tenant, self.tenant)
        self.assertEqual(cart.status, Cart.Status.ACTIVE)

    def test_get_or_create_cart_reuses_guest_cart(self):
        request = SimpleNamespace(
            user=AnonymousUser(),
            tenant=self.tenant,
            session=SessionStore(),
        )
        existing_cart = CartService.get_or_create_cart(request)

        cart = CartService.get_or_create_cart(request)

        self.assertEqual(cart, existing_cart)
        self.assertEqual(
            Cart.objects.filter(session_key=request.session.session_key).count(),
            1,
        )

    def test_get_or_create_cart_requires_session_for_guest(self):
        request = SimpleNamespace(user=AnonymousUser(), tenant=self.tenant)

        with self.assertRaisesMessage(
            ValueError,
            'Cart requests require session middleware.',
        ):
            CartService.get_or_create_cart(request)

    def test_get_cart_endpoint_returns_authenticated_cart(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse('cart-detail'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Cart.Status.ACTIVE)
        self.assertEqual(response.data['items'], [])
        self.assertEqual(response.data['total_items'], 0)
        self.assertEqual(response.data['subtotal'], '0.00')
        self.assertTrue(Cart.objects.filter(user=self.user).exists())

    def test_get_cart_endpoint_returns_guest_cart(self):
        response = self.client.get(reverse('cart-detail'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Cart.Status.ACTIVE)
        self.assertEqual(response.data['items'], [])
        self.assertEqual(response.data['total_items'], 0)
        self.assertEqual(response.data['subtotal'], '0.00')
        self.assertEqual(Cart.objects.filter(user__isnull=True).count(), 1)

    @patch.object(CartService, 'get_or_create_cart')
    @patch.object(CartRedisCache, 'get_cart')
    def test_get_serialized_cart_returns_redis_payload_for_guest(
        self,
        get_cart,
        get_or_create_cart,
    ):
        request = SimpleNamespace(
            user=AnonymousUser(),
            tenant=self.tenant,
            session=SessionStore(),
        )
        request.session.create()
        get_cart.return_value = {
            'id': 1,
            'status': Cart.Status.ACTIVE,
            'items': [],
            'total_items': 0,
            'subtotal': '0.00',
        }

        payload = CartService.get_serialized_cart(request)

        self.assertEqual(payload, get_cart.return_value)
        get_cart.assert_called_once_with(request.session.session_key)
        get_or_create_cart.assert_not_called()

    @patch.object(CartService, '_store_cart_after_commit')
    @patch.object(CartRedisCache, 'get_cart')
    def test_get_serialized_cart_falls_back_to_db_on_redis_miss(
        self,
        get_cart,
        store_cart_after_commit,
    ):
        request = SimpleNamespace(
            user=AnonymousUser(),
            tenant=self.tenant,
            session=SessionStore(),
        )
        get_cart.return_value = None

        payload = CartService.get_serialized_cart(request)

        self.assertEqual(payload['status'], Cart.Status.ACTIVE)
        self.assertEqual(payload['items'], [])
        self.assertEqual(payload['total_items'], 0)
        self.assertEqual(payload['subtotal'], '0.00')
        self.assertTrue(Cart.objects.filter(user__isnull=True).exists())
        store_cart_after_commit.assert_called_once()

    @patch('cart.services.transaction.on_commit')
    def test_invalidate_cart_after_commit_schedules_session_key_delete(
        self,
        on_commit,
    ):
        cart = SimpleNamespace(session_key='guest-session-123')

        CartService._invalidate_cart_after_commit(cart)

        on_commit.assert_called_once()
        callback = on_commit.call_args.args[0]

        with patch.object(CartService, '_invalidate_cart') as invalidate_cart:
            callback()

        invalidate_cart.assert_called_once_with('guest-session-123')

    @patch('cart.services.transaction.on_commit')
    def test_invalidate_cart_after_commit_skips_carts_without_session(
        self,
        on_commit,
    ):
        cart = SimpleNamespace(session_key=None)

        CartService._invalidate_cart_after_commit(cart)

        on_commit.assert_not_called()


class CartItemEndpointTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store',
            domain='acme.example.com',
            plan='basic',
        )
        self.user = User.objects.create_user(
            email='customer@example.com',
            password='StrongPass123',
            first_name='Customer',
            last_name='User',
            role='customer',
            tenant=self.tenant,
        )
        self.client.force_authenticate(user=self.user)

    def test_post_cart_items_adds_product_variant_to_cart(self):
        product_variant = self._create_product_variant(stock_quantity=5)

        response = self.client.post(
            reverse('cart-item-list'),
            {
                'product_variant_id': product_variant.id,
                'quantity': 2,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['product_variant_id'], product_variant.id)
        self.assertEqual(response.data['quantity'], 2)
        self.assertEqual(response.data['unit_price'], '999.00')
        self.assertEqual(response.data['line_total'], '1998.00')

        cart = Cart.objects.get(user=self.user)
        item = cart.items.get(product_variant=product_variant)
        self.assertEqual(item.quantity, 2)

    def test_post_cart_items_increments_existing_item(self):
        product_variant = self._create_product_variant(stock_quantity=5)
        url = reverse('cart-item-list')

        self.client.post(
            url,
            {'product_variant_id': product_variant.id, 'quantity': 2},
            format='json',
        )
        response = self.client.post(
            url,
            {'product_variant_id': product_variant.id, 'quantity': 1},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['quantity'], 3)
        self.assertEqual(
            Cart.objects.get(user=self.user).items.filter(
                product_variant=product_variant,
            ).count(),
            1,
        )

    def test_post_cart_items_rejects_quantity_above_stock(self):
        product_variant = self._create_product_variant(stock_quantity=1)

        response = self.client.post(
            reverse('cart-item-list'),
            {
                'product_variant_id': product_variant.id,
                'quantity': 2,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('quantity', response.data)
        self.assertFalse(Cart.objects.get(user=self.user).items.exists())

    def test_post_cart_items_rejects_increment_above_stock(self):
        product_variant = self._create_product_variant(stock_quantity=3)
        url = reverse('cart-item-list')

        self.client.post(
            url,
            {'product_variant_id': product_variant.id, 'quantity': 2},
            format='json',
        )
        response = self.client.post(
            url,
            {'product_variant_id': product_variant.id, 'quantity': 2},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('quantity', response.data)

        item = Cart.objects.get(user=self.user).items.get()
        self.assertEqual(item.quantity, 2)

    def test_patch_cart_item_updates_quantity(self):
        product_variant = self._create_product_variant(stock_quantity=5)
        create_response = self.client.post(
            reverse('cart-item-list'),
            {'product_variant_id': product_variant.id, 'quantity': 2},
            format='json',
        )

        response = self.client.patch(
            reverse('cart-item-detail', args=[create_response.data['id']]),
            {'quantity': 4},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['quantity'], 4)
        self.assertEqual(response.data['line_total'], '3996.00')

        item = Cart.objects.get(user=self.user).items.get()
        self.assertEqual(item.quantity, 4)

    def test_patch_cart_item_rejects_quantity_above_stock(self):
        product_variant = self._create_product_variant(stock_quantity=3)
        create_response = self.client.post(
            reverse('cart-item-list'),
            {'product_variant_id': product_variant.id, 'quantity': 2},
            format='json',
        )

        response = self.client.patch(
            reverse('cart-item-detail', args=[create_response.data['id']]),
            {'quantity': 4},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('quantity', response.data)

        item = Cart.objects.get(user=self.user).items.get()
        self.assertEqual(item.quantity, 2)

    def test_patch_cart_item_rejects_item_outside_current_cart(self):
        other_user = User.objects.create_user(
            email='other@example.com',
            password='StrongPass123',
            first_name='Other',
            last_name='Customer',
            role='customer',
            tenant=self.tenant,
        )
        product_variant = self._create_product_variant(stock_quantity=5)

        self.client.force_authenticate(user=other_user)
        create_response = self.client.post(
            reverse('cart-item-list'),
            {'product_variant_id': product_variant.id, 'quantity': 2},
            format='json',
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            reverse('cart-item-detail', args=[create_response.data['id']]),
            {'quantity': 3},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_cart_item_removes_item_from_cart(self):
        product_variant = self._create_product_variant(stock_quantity=5)
        create_response = self.client.post(
            reverse('cart-item-list'),
            {'product_variant_id': product_variant.id, 'quantity': 2},
            format='json',
        )

        response = self.client.delete(
            reverse('cart-item-detail', args=[create_response.data['id']]),
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Cart.objects.get(user=self.user).items.exists())

    def test_delete_cart_item_removes_only_target_item(self):
        first_variant = self._create_product_variant(
            stock_quantity=5,
            sku='PHONE-PRO',
            slug='phone-pro',
        )
        second_variant = self._create_product_variant(
            stock_quantity=5,
            sku='PHONE-AIR',
            slug='phone-air',
        )
        first_response = self.client.post(
            reverse('cart-item-list'),
            {'product_variant_id': first_variant.id, 'quantity': 1},
            format='json',
        )
        self.client.post(
            reverse('cart-item-list'),
            {'product_variant_id': second_variant.id, 'quantity': 2},
            format='json',
        )

        response = self.client.delete(
            reverse('cart-item-detail', args=[first_response.data['id']]),
        )

        cart = Cart.objects.get(user=self.user)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(cart.items.filter(product_variant=first_variant).exists())
        self.assertTrue(cart.items.filter(product_variant=second_variant).exists())

    def test_delete_cart_item_rejects_item_outside_current_cart(self):
        other_user = User.objects.create_user(
            email='delete-other@example.com',
            password='StrongPass123',
            first_name='Other',
            last_name='Customer',
            role='customer',
            tenant=self.tenant,
        )
        product_variant = self._create_product_variant(stock_quantity=5)

        self.client.force_authenticate(user=other_user)
        create_response = self.client.post(
            reverse('cart-item-list'),
            {'product_variant_id': product_variant.id, 'quantity': 2},
            format='json',
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.delete(
            reverse('cart-item-detail', args=[create_response.data['id']]),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Cart.objects.get(user=other_user).items.exists())

    def _create_product_variant(
        self,
        stock_quantity,
        sku='PHONE-PRO',
        slug='phone-pro',
    ):
        Brand = apps.get_model('catalog', 'Brand')
        Category = apps.get_model('catalog', 'Category')
        Product = apps.get_model('catalog', 'Product')
        ProductVariant = apps.get_model('catalog', 'ProductVariant')

        brand, _ = Brand.objects.get_or_create(
            slug='acme',
            tenant=self.tenant,
            defaults={
                'name': 'Acme',
            },
        )
        category, _ = Category.objects.get_or_create(
            slug='phones',
            tenant=self.tenant,
            defaults={
                'name': 'Phones',
            },
        )
        product = Product.objects.create(
            name='Phone Pro',
            slug=slug,
            sku=sku,
            brand=brand,
            category=category,
            status='active',
            base_price='999.00',
            tenant=self.tenant,
        )
        return ProductVariant.objects.create(
            product=product,
            color='Black',
            storage='256GB',
            ram='8GB',
            variant_price='999.00',
            stock_quantity=stock_quantity,
            tenant=self.tenant,
        )
