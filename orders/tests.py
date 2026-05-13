from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from django.urls import reverse
from django_fsm import TransitionNotAllowed, can_proceed
from rest_framework import status
from rest_framework.test import APITestCase

from cart.models import Cart
from checkout.models import CheckoutSession
from tenants.models import Tenant
from users.models import User

from .models import Order, OrderEvent


class OrderStateMachineTests(SimpleTestCase):
    def test_all_valid_transitions_move_to_expected_statuses(self):
        transitions = [
            (
                Order.Status.PENDING,
                'confirm',
                Order.Status.CONFIRMED,
            ),
            (
                Order.Status.CONFIRMED,
                'mark_processing',
                Order.Status.PROCESSING,
            ),
            (
                Order.Status.PROCESSING,
                'mark_shipped',
                Order.Status.SHIPPED,
            ),
            (
                Order.Status.SHIPPED,
                'mark_delivered',
                Order.Status.DELIVERED,
            ),
            (
                Order.Status.PENDING,
                'cancel',
                Order.Status.CANCELLED,
            ),
        ]

        for source, method_name, target in transitions:
            with self.subTest(source=source, transition=method_name):
                order = Order(status=source)
                transition_method = getattr(order, method_name)

                self.assertTrue(can_proceed(transition_method))
                transition_method()

                self.assertEqual(order.status, target)

    def test_order_rejects_invalid_transitions(self):
        invalid_transitions = [
            (Order.Status.PENDING, 'mark_processing'),
            (Order.Status.PENDING, 'mark_shipped'),
            (Order.Status.PENDING, 'mark_delivered'),
            (Order.Status.CONFIRMED, 'confirm'),
            (Order.Status.CONFIRMED, 'mark_shipped'),
            (Order.Status.CONFIRMED, 'mark_delivered'),
            (Order.Status.CONFIRMED, 'cancel'),
            (Order.Status.PROCESSING, 'confirm'),
            (Order.Status.PROCESSING, 'mark_processing'),
            (Order.Status.PROCESSING, 'mark_delivered'),
            (Order.Status.PROCESSING, 'cancel'),
            (Order.Status.SHIPPED, 'confirm'),
            (Order.Status.SHIPPED, 'mark_processing'),
            (Order.Status.SHIPPED, 'mark_shipped'),
            (Order.Status.SHIPPED, 'cancel'),
            (Order.Status.DELIVERED, 'confirm'),
            (Order.Status.DELIVERED, 'mark_processing'),
            (Order.Status.DELIVERED, 'mark_shipped'),
            (Order.Status.DELIVERED, 'mark_delivered'),
            (Order.Status.DELIVERED, 'cancel'),
            (Order.Status.CANCELLED, 'confirm'),
            (Order.Status.CANCELLED, 'mark_processing'),
            (Order.Status.CANCELLED, 'mark_shipped'),
            (Order.Status.CANCELLED, 'mark_delivered'),
            (Order.Status.CANCELLED, 'cancel'),
        ]

        for source, method_name in invalid_transitions:
            with self.subTest(source=source, transition=method_name):
                order = Order(status=source)
                transition_method = getattr(order, method_name)

                self.assertFalse(can_proceed(transition_method))
                with self.assertRaises(TransitionNotAllowed):
                    transition_method()
                self.assertEqual(order.status, source)


class OrderEventAuditTrailTests(TestCase):
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


class CustomerOrderListEndpointTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='customer-orders-store',
            domain='customer-orders.example.com',
            plan='basic',
        )
        self.customer = User.objects.create_user(
            email='customer-list@example.com',
            password='StrongPass123',
            first_name='Customer',
            last_name='User',
            role='customer',
            tenant=self.tenant,
        )
        self.other_customer = User.objects.create_user(
            email='other-customer-list@example.com',
            password='StrongPass123',
            first_name='Other',
            last_name='Customer',
            role='customer',
            tenant=self.tenant,
        )
        self.vendor = User.objects.create_user(
            email='vendor-list@example.com',
            password='StrongPass123',
            first_name='Vendor',
            last_name='Admin',
            role='vendor_admin',
            tenant=self.tenant,
        )

    def test_customer_can_list_own_orders(self):
        first_order = self._create_order(idempotency_key='customer-list-1')
        second_order = self._create_order(idempotency_key='customer-list-2')
        other_order = self._create_order(
            user=self.other_customer,
            idempotency_key='other-customer-list',
        )
        self.client.force_authenticate(user=self.customer)

        response = self.client.get(reverse('customer-order-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order_ids = {order['id'] for order in response.data}
        self.assertEqual(order_ids, {first_order.id, second_order.id})
        self.assertNotIn(other_order.id, order_ids)

    def test_customer_order_list_requires_customer_role(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(reverse('customer-order-list'))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_can_retrieve_own_order_by_order_number(self):
        order = self._create_order(idempotency_key='customer-detail-key')
        self.client.force_authenticate(user=self.customer)

        response = self.client.get(
            reverse('customer-order-detail', args=[order.order_number]),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], order.id)
        self.assertEqual(response.data['order_number'], order.order_number)

    def test_customer_order_detail_returns_not_found_for_other_customer_order(self):
        order = self._create_order(
            user=self.other_customer,
            idempotency_key='other-customer-detail-key',
        )
        self.client.force_authenticate(user=self.customer)

        response = self.client.get(
            reverse('customer-order-detail', args=[order.order_number]),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_customer_order_detail_requires_customer_role(self):
        order = self._create_order(idempotency_key='vendor-detail-key')
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(
            reverse('customer-order-detail', args=[order.order_number]),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_can_cancel_pending_order(self):
        order = self._create_order(idempotency_key='customer-cancel-key')
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            reverse('customer-order-cancel', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Order.Status.CANCELLED)
        updated_order = Order.objects.get(pk=order.pk)
        self.assertEqual(updated_order.status, Order.Status.CANCELLED)

    def test_customer_cancel_rejects_non_pending_order(self):
        order = self._create_order(idempotency_key='customer-cancel-confirmed')
        order.confirm()
        order.save(update_fields=['status', 'updated_at'])
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            reverse('customer-order-cancel', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot be cancelled', response.data['detail'])

    def test_customer_cancel_returns_not_found_for_other_customer_order(self):
        order = self._create_order(
            user=self.other_customer,
            idempotency_key='other-customer-cancel-key',
        )
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            reverse('customer-order-cancel', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_customer_cancel_requires_customer_role(self):
        order = self._create_order(idempotency_key='vendor-cancel-key')
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            reverse('customer-order-cancel', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def _create_order(
        self,
        user=None,
        idempotency_key='customer-list-key',
    ):
        user = user or self.customer
        cart = Cart.objects.create(
            user=user,
            tenant=user.tenant,
        )
        checkout_session = CheckoutSession.objects.create(
            user=user,
            cart=cart,
            idempotency_key=idempotency_key,
            shipping_address={
                'full_name': 'Customer User',
                'line1': 'Main street 1',
                'city': 'Prishtina',
                'postal_code': '10000',
                'country': 'Kosovo',
            },
            status=CheckoutSession.Status.READY,
            tenant=user.tenant,
        )
        return Order.objects.create(
            user=user,
            checkout_session=checkout_session,
            shipping_address={
                'full_name': 'Customer User',
                'line1': 'Main street 1',
                'city': 'Prishtina',
                'postal_code': '10000',
                'country': 'Kosovo',
            },
            subtotal=Decimal('99.00'),
            total_amount=Decimal('99.00'),
            tenant=user.tenant,
        )


class VendorOrderConfirmEndpointTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store',
            domain='acme.example.com',
            plan='basic',
        )
        self.vendor = User.objects.create_user(
            email='vendor@example.com',
            password='StrongPass123',
            first_name='Vendor',
            last_name='Admin',
            role='vendor_admin',
            tenant=self.tenant,
        )
        self.customer = User.objects.create_user(
            email='customer@example.com',
            password='StrongPass123',
            first_name='Customer',
            last_name='User',
            role='customer',
            tenant=self.tenant,
        )
        self.store_staff = User.objects.create_user(
            email='staff@example.com',
            password='StrongPass123',
            first_name='Store',
            last_name='Staff',
            role='store_staff',
            tenant=self.tenant,
        )

    def test_vendor_can_list_orders(self):
        first_order = self._create_order(idempotency_key='checkout-key-1')
        second_order = self._create_order(idempotency_key='checkout-key-2')
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(reverse('vendor-order-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order_ids = {order['id'] for order in response.data}
        self.assertEqual(order_ids, {first_order.id, second_order.id})

    def test_vendor_order_list_filters_by_status(self):
        pending_order = self._create_order(idempotency_key='pending-key')
        confirmed_order = self._create_order(idempotency_key='confirmed-key')
        confirmed_order.confirm()
        confirmed_order.save(update_fields=['status', 'updated_at'])
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(
            reverse('vendor-order-list'),
            {'status': Order.Status.CONFIRMED},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [order['id'] for order in response.data],
            [confirmed_order.id],
        )
        self.assertNotIn(
            pending_order.id,
            [order['id'] for order in response.data],
        )

    def test_vendor_order_list_filters_by_date_range(self):
        today_order = self._create_order(idempotency_key='today-key')
        old_order = self._create_order(idempotency_key='old-key')
        old_created_at = timezone.now() - timezone.timedelta(days=5)
        Order.objects.filter(pk=old_order.pk).update(created_at=old_created_at)
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(
            reverse('vendor-order-list'),
            {
                'date_from': timezone.localdate().isoformat(),
                'date_to': timezone.localdate().isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [order['id'] for order in response.data],
            [today_order.id],
        )

    def test_vendor_order_list_rejects_invalid_filters(self):
        self.client.force_authenticate(user=self.vendor)

        invalid_status_response = self.client.get(
            reverse('vendor-order-list'),
            {'status': 'lost'},
        )
        invalid_date_response = self.client.get(
            reverse('vendor-order-list'),
            {'date_from': 'not-a-date'},
        )

        self.assertEqual(
            invalid_status_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            invalid_date_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_vendor_order_list_requires_vendor_admin_role(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.get(reverse('vendor-order-list'))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendor_order_list_is_scoped_to_vendor_tenant(self):
        own_order = self._create_order(idempotency_key='own-key')
        other_tenant = Tenant.objects.create(
            name='Other List Store',
            slug='other-list-store',
            domain='list.other.example.com',
            plan='basic',
        )
        other_customer = User.objects.create_user(
            email='list-other-customer@example.com',
            password='StrongPass123',
            first_name='Other',
            last_name='Customer',
            role='customer',
            tenant=other_tenant,
        )
        other_order = self._create_order(
            user=other_customer,
            tenant=other_tenant,
            idempotency_key='other-list-key',
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.get(reverse('vendor-order-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order_ids = {order['id'] for order in response.data}
        self.assertEqual(order_ids, {own_order.id})
        self.assertNotIn(other_order.id, order_ids)

    def test_vendor_can_confirm_pending_order(self):
        order = self._create_order()
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            reverse('vendor-order-confirm', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Order.Status.CONFIRMED)
        updated_order = Order.objects.get(pk=order.pk)
        self.assertEqual(updated_order.status, Order.Status.CONFIRMED)
        self.assertTrue(
            updated_order.events.filter(
                from_status=Order.Status.PENDING,
                to_status=Order.Status.CONFIRMED,
                transition='confirm',
            ).exists(),
        )

    def test_vendor_confirm_rejects_non_pending_order(self):
        order = self._create_order()
        order.confirm()
        order.save(update_fields=['status', 'updated_at'])
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            reverse('vendor-order-confirm', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot be confirmed', response.data['detail'])

    def test_vendor_confirm_requires_vendor_admin_role(self):
        order = self._create_order()
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            reverse('vendor-order-confirm', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_transition_endpoints_reject_store_staff_role(self):
        order = self._create_order(idempotency_key='staff-role-key')
        endpoint_names = [
            'vendor-order-confirm',
            'vendor-order-mark-shipped',
            'vendor-order-mark-delivered',
        ]
        self.client.force_authenticate(user=self.store_staff)

        for endpoint_name in endpoint_names:
            with self.subTest(endpoint=endpoint_name):
                response = self.client.post(
                    reverse(endpoint_name, args=[order.id]),
                    {},
                    format='json',
                )

                self.assertEqual(
                    response.status_code,
                    status.HTTP_403_FORBIDDEN,
                )

    def test_vendor_confirm_returns_not_found_for_other_tenant_order(self):
        other_tenant = Tenant.objects.create(
            name='Other Store',
            slug='other-store',
            domain='other.example.com',
            plan='basic',
        )
        other_customer = User.objects.create_user(
            email='other-customer@example.com',
            password='StrongPass123',
            first_name='Other',
            last_name='Customer',
            role='customer',
            tenant=other_tenant,
        )
        order = self._create_order(
            user=other_customer,
            tenant=other_tenant,
            idempotency_key='other-checkout-key',
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            reverse('vendor-order-confirm', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_vendor_can_mark_processing_order_shipped(self):
        order = self._create_order()
        order.confirm()
        order.mark_processing()
        order.save(update_fields=['status', 'updated_at'])
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            reverse('vendor-order-mark-shipped', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Order.Status.SHIPPED)
        updated_order = Order.objects.get(pk=order.pk)
        self.assertEqual(updated_order.status, Order.Status.SHIPPED)
        self.assertTrue(
            updated_order.events.filter(
                from_status=Order.Status.PROCESSING,
                to_status=Order.Status.SHIPPED,
                transition='mark_shipped',
            ).exists(),
        )

    def test_vendor_mark_shipped_rejects_non_processing_order(self):
        order = self._create_order()
        order.confirm()
        order.save(update_fields=['status', 'updated_at'])
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            reverse('vendor-order-mark-shipped', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('marked shipped', response.data['detail'])

    def test_vendor_mark_shipped_requires_vendor_admin_role(self):
        order = self._create_order()
        order.confirm()
        order.mark_processing()
        order.save(update_fields=['status', 'updated_at'])
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            reverse('vendor-order-mark-shipped', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendor_mark_shipped_returns_not_found_for_other_tenant_order(self):
        other_tenant = Tenant.objects.create(
            name='Other Store',
            slug='other-store-ship',
            domain='ship.other.example.com',
            plan='basic',
        )
        other_customer = User.objects.create_user(
            email='ship-other-customer@example.com',
            password='StrongPass123',
            first_name='Other',
            last_name='Customer',
            role='customer',
            tenant=other_tenant,
        )
        order = self._create_order(
            user=other_customer,
            tenant=other_tenant,
            idempotency_key='ship-other-checkout-key',
        )
        order.confirm()
        order.mark_processing()
        order.save(update_fields=['status', 'updated_at'])
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            reverse('vendor-order-mark-shipped', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_vendor_can_mark_shipped_order_delivered(self):
        order = self._create_order()
        order.confirm()
        order.mark_processing()
        order.mark_shipped()
        order.save(update_fields=['status', 'updated_at'])
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            reverse('vendor-order-mark-delivered', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Order.Status.DELIVERED)
        updated_order = Order.objects.get(pk=order.pk)
        self.assertEqual(updated_order.status, Order.Status.DELIVERED)
        self.assertTrue(
            updated_order.events.filter(
                from_status=Order.Status.SHIPPED,
                to_status=Order.Status.DELIVERED,
                transition='mark_delivered',
            ).exists(),
        )

    def test_vendor_mark_delivered_rejects_non_shipped_order(self):
        order = self._create_order()
        order.confirm()
        order.mark_processing()
        order.save(update_fields=['status', 'updated_at'])
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            reverse('vendor-order-mark-delivered', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('marked delivered', response.data['detail'])

    def test_vendor_mark_delivered_requires_vendor_admin_role(self):
        order = self._create_order()
        order.confirm()
        order.mark_processing()
        order.mark_shipped()
        order.save(update_fields=['status', 'updated_at'])
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            reverse('vendor-order-mark-delivered', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendor_mark_delivered_returns_not_found_for_other_tenant_order(self):
        other_tenant = Tenant.objects.create(
            name='Other Delivered Store',
            slug='other-delivered-store',
            domain='delivered.other.example.com',
            plan='basic',
        )
        other_customer = User.objects.create_user(
            email='delivered-other-customer@example.com',
            password='StrongPass123',
            first_name='Other',
            last_name='Customer',
            role='customer',
            tenant=other_tenant,
        )
        order = self._create_order(
            user=other_customer,
            tenant=other_tenant,
            idempotency_key='delivered-other-checkout-key',
        )
        order.confirm()
        order.mark_processing()
        order.mark_shipped()
        order.save(update_fields=['status', 'updated_at'])
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            reverse('vendor-order-mark-delivered', args=[order.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def _create_order(
        self,
        user=None,
        tenant=None,
        idempotency_key='checkout-key-123',
    ):
        user = user or self.customer
        tenant = tenant or self.tenant
        cart = Cart.objects.create(
            user=user,
            tenant=tenant,
        )
        checkout_session = CheckoutSession.objects.create(
            user=user,
            cart=cart,
            idempotency_key=idempotency_key,
            shipping_address={
                'full_name': 'Customer User',
                'line1': 'Main street 1',
                'city': 'Prishtina',
                'postal_code': '10000',
                'country': 'Kosovo',
            },
            status=CheckoutSession.Status.READY,
            tenant=tenant,
        )
        return Order.objects.create(
            user=user,
            checkout_session=checkout_session,
            shipping_address={
                'full_name': 'Customer User',
                'line1': 'Main street 1',
                'city': 'Prishtina',
                'postal_code': '10000',
                'country': 'Kosovo',
            },
            subtotal=Decimal('99.00'),
            total_amount=Decimal('99.00'),
            tenant=tenant,
        )

    def test_order_transition_creates_audit_event(self):
        order = self._create_order()

        order.confirm()
        order.save(update_fields=['status', 'updated_at'])

        event = order.events.get()
        self.assertEqual(event.from_status, Order.Status.PENDING)
        self.assertEqual(event.to_status, Order.Status.CONFIRMED)
        self.assertEqual(event.transition, 'confirm')
        self.assertEqual(event.tenant, self.tenant)

    @patch('orders.models.send_order_status_email.delay')
    def test_order_transition_queues_status_email_after_commit(self, delay):
        order = self._create_order()

        with self.captureOnCommitCallbacks(execute=True):
            order.confirm()
            order.save(update_fields=['status', 'updated_at'])

        delay.assert_called_once_with(order.pk, Order.Status.CONFIRMED)

    def test_invalid_transition_does_not_create_audit_event(self):
        order = self._create_order()

        with self.assertRaises(TransitionNotAllowed):
            order.mark_shipped()

        self.assertFalse(OrderEvent.objects.exists())

    def test_each_transition_is_logged_in_order(self):
        order = self._create_order()

        order.confirm()
        order.save(update_fields=['status', 'updated_at'])
        order.mark_processing()
        order.save(update_fields=['status', 'updated_at'])

        events = list(order.events.values_list(
            'from_status',
            'to_status',
            'transition',
        ))
        self.assertEqual(
            events,
            [
                (
                    Order.Status.PENDING,
                    Order.Status.CONFIRMED,
                    'confirm',
                ),
                (
                    Order.Status.CONFIRMED,
                    Order.Status.PROCESSING,
                    'mark_processing',
                ),
            ],
        )

    def _create_order(self):
        cart = Cart.objects.create(
            user=self.user,
            tenant=self.tenant,
        )
        checkout_session = CheckoutSession.objects.create(
            user=self.user,
            cart=cart,
            idempotency_key='checkout-key-123',
            shipping_address={
                'full_name': 'Customer User',
                'line1': 'Main street 1',
                'city': 'Prishtina',
                'postal_code': '10000',
                'country': 'Kosovo',
            },
            status=CheckoutSession.Status.READY,
            tenant=self.tenant,
        )
        return Order.objects.create(
            user=self.user,
            checkout_session=checkout_session,
            shipping_address={
                'full_name': 'Customer User',
                'line1': 'Main street 1',
                'city': 'Prishtina',
                'postal_code': '10000',
                'country': 'Kosovo',
            },
            subtotal=Decimal('99.00'),
            total_amount=Decimal('99.00'),
            tenant=self.tenant,
        )
