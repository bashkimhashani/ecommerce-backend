from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from tenants.models import Tenant

from .models import Cart
from .services import CartService


User = get_user_model()


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

    def test_post_cart_items_adds_product_variant_to_cart(self):
        product_variant = self._create_product_variant(stock_quantity=5)
        self.client.force_authenticate(user=self.user)

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
        self.client.force_authenticate(user=self.user)
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
        self.client.force_authenticate(user=self.user)

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

    def test_patch_cart_item_updates_quantity(self):
        product_variant = self._create_product_variant(stock_quantity=5)
        self.client.force_authenticate(user=self.user)
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
        self.client.force_authenticate(user=self.user)
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

    def _create_product_variant(self, stock_quantity):
        Brand = apps.get_model('catalog', 'Brand')
        Category = apps.get_model('catalog', 'Category')
        Product = apps.get_model('catalog', 'Product')
        ProductVariant = apps.get_model('catalog', 'ProductVariant')

        brand = Brand.objects.create(
            name='Acme',
            slug='acme',
            tenant=self.tenant,
        )
        category = Category.objects.create(
            name='Phones',
            slug='phones',
            tenant=self.tenant,
        )
        product = Product.objects.create(
            name='Phone Pro',
            slug='phone-pro',
            sku='PHONE-PRO',
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
