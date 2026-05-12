from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from cart.models import Cart, CartItem
from tenants.models import Tenant

from .models import CheckoutSession
from .serializers import AddressSerializer


User = get_user_model()


class CheckoutSessionEndpointTests(APITestCase):
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

    def test_post_checkout_session_creates_session_for_active_cart(self):
        cart = self._create_cart_with_item()

        response = self.client.post(
            reverse('checkout-session'),
            {
                'idempotency_key': 'checkout-key-123',
                'shipping_address': self._address_payload(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['cart_id'], cart.id)
        self.assertEqual(response.data['idempotency_key'], 'checkout-key-123')
        self.assertEqual(response.data['status'], CheckoutSession.Status.PENDING)
        self.assertEqual(
            response.data['shipping_address']['city'],
            'Prishtina',
        )
        checkout_session = CheckoutSession.objects.get(
            id=response.data['id'],
        )
        self.assertEqual(checkout_session.user, self.user)
        self.assertEqual(checkout_session.cart, cart)
        self.assertEqual(checkout_session.tenant, self.tenant)
        self.assertEqual(checkout_session.status, CheckoutSession.Status.PENDING)
        self.assertEqual(
            checkout_session.shipping_address['postal_code'],
            '10000',
        )

    def test_post_checkout_session_validates_shipping_address_fields(self):
        self._create_cart_with_item()

        response = self.client.post(
            reverse('checkout-session'),
            {
                'idempotency_key': 'checkout-key-123',
                'shipping_address': {
                    'city': 'Prishtina',
                    'line1': 'Main street 1',
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('full_name', response.data['shipping_address'])
        self.assertIn('postal_code', response.data['shipping_address'])

    def test_post_checkout_session_reuses_existing_idempotency_key(self):
        self._create_cart_with_item()

        first_response = self.client.post(
            reverse('checkout-session'),
            {'idempotency_key': 'checkout-key-123'},
            format='json',
        )
        second_response = self.client.post(
            reverse('checkout-session'),
            {'idempotency_key': 'checkout-key-123'},
            format='json',
        )

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data['id'], second_response.data['id'])
        self.assertEqual(CheckoutSession.objects.count(), 1)

    def test_post_checkout_session_accepts_idempotency_key_header(self):
        self._create_cart_with_item()

        response = self.client.post(
            reverse('checkout-session'),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='checkout-key-123',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['idempotency_key'], 'checkout-key-123')

    def test_post_checkout_session_rejects_empty_cart(self):
        Cart.objects.create(user=self.user, tenant=self.tenant)

        response = self.client.post(
            reverse('checkout-session'),
            {'idempotency_key': 'checkout-key-123'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('empty cart', response.data['detail'])

    def test_post_checkout_session_requires_customer_role(self):
        vendor = User.objects.create_user(
            email='vendor@example.com',
            password='StrongPass123',
            first_name='Vendor',
            last_name='Admin',
            role='vendor_admin',
            tenant=self.tenant,
        )
        self.client.force_authenticate(user=vendor)

        response = self.client.post(
            reverse('checkout-session'),
            {'idempotency_key': 'checkout-key-123'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_checkout_session_address_updates_shipping_address(self):
        cart = self._create_cart_with_item()
        checkout_session = CheckoutSession.objects.create(
            user=self.user,
            cart=cart,
            idempotency_key='checkout-key-123',
            tenant=self.tenant,
        )

        response = self.client.patch(
            reverse('checkout-session-address', args=[checkout_session.id]),
            self._address_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], CheckoutSession.Status.READY)
        self.assertEqual(
            response.data['shipping_address']['line1'],
            'Main street 1',
        )
        checkout_session.refresh_from_db()
        self.assertEqual(checkout_session.status, CheckoutSession.Status.READY)
        self.assertEqual(
            checkout_session.shipping_address['full_name'],
            'Customer User',
        )

    def test_patch_checkout_session_address_validates_required_fields(self):
        cart = self._create_cart_with_item()
        checkout_session = CheckoutSession.objects.create(
            user=self.user,
            cart=cart,
            idempotency_key='checkout-key-123',
            tenant=self.tenant,
        )

        response = self.client.patch(
            reverse('checkout-session-address', args=[checkout_session.id]),
            {
                'city': 'Prishtina',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('line1', response.data)
        self.assertIn('postal_code', response.data)

    def test_address_serializer_rejects_missing_required_fields(self):
        serializer = AddressSerializer(data={
            'city': 'Prishtina',
            'line1': 'Main street 1',
        })

        self.assertFalse(serializer.is_valid())
        self.assertIn('full_name', serializer.errors)
        self.assertIn('phone', serializer.errors)
        self.assertIn('postal_code', serializer.errors)
        self.assertIn('country', serializer.errors)

    def test_patch_checkout_session_address_rejects_blank_required_fields(self):
        cart = self._create_cart_with_item()
        checkout_session = CheckoutSession.objects.create(
            user=self.user,
            cart=cart,
            idempotency_key='checkout-key-123',
            tenant=self.tenant,
        )
        payload = self._address_payload()
        payload['full_name'] = ''
        payload['line1'] = ''

        response = self.client.patch(
            reverse('checkout-session-address', args=[checkout_session.id]),
            payload,
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('full_name', response.data)
        self.assertIn('line1', response.data)

    def test_patch_checkout_session_address_rejects_other_customer_session(self):
        other_user = User.objects.create_user(
            email='other@example.com',
            password='StrongPass123',
            first_name='Other',
            last_name='Customer',
            role='customer',
            tenant=self.tenant,
        )
        cart = self._create_cart_with_item(user=other_user)
        checkout_session = CheckoutSession.objects.create(
            user=other_user,
            cart=cart,
            idempotency_key='checkout-key-123',
            tenant=self.tenant,
        )

        response = self.client.patch(
            reverse('checkout-session-address', args=[checkout_session.id]),
            self._address_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_checkout_session_address_requires_customer_role(self):
        vendor = User.objects.create_user(
            email='vendor@example.com',
            password='StrongPass123',
            first_name='Vendor',
            last_name='Admin',
            role='vendor_admin',
            tenant=self.tenant,
        )
        cart = self._create_cart_with_item()
        checkout_session = CheckoutSession.objects.create(
            user=self.user,
            cart=cart,
            idempotency_key='checkout-key-123',
            tenant=self.tenant,
        )
        self.client.force_authenticate(user=vendor)

        response = self.client.patch(
            reverse('checkout-session-address', args=[checkout_session.id]),
            self._address_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def _address_payload(self):
        return {
            'full_name': 'Customer User',
            'phone': '+38344111222',
            'line1': 'Main street 1',
            'line2': 'Apartment 4',
            'city': 'Prishtina',
            'state': '',
            'postal_code': '10000',
            'country': 'Kosovo',
        }

    def _create_cart_with_item(self, user=None):
        cart = Cart.objects.create(
            user=user or self.user,
            tenant=self.tenant,
        )
        product_variant = self._create_product_variant()
        CartItem.objects.create(
            cart=cart,
            product_variant=product_variant,
            quantity=1,
            unit_price=product_variant.variant_price,
            tenant=self.tenant,
        )
        return cart

    def _create_product_variant(self):
        Brand = apps.get_model('catalog', 'Brand')
        Category = apps.get_model('catalog', 'Category')
        Product = apps.get_model('catalog', 'Product')
        ProductVariant = apps.get_model('catalog', 'ProductVariant')

        brand, _ = Brand.objects.get_or_create(
            slug='acme',
            tenant=self.tenant,
            defaults={'name': 'Acme'},
        )
        category, _ = Category.objects.get_or_create(
            slug='phones',
            tenant=self.tenant,
            defaults={'name': 'Phones'},
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
            stock_quantity=5,
            tenant=self.tenant,
        )
