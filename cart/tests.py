from types import SimpleNamespace

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
