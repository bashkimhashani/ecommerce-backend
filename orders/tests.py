from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django_fsm import TransitionNotAllowed, can_proceed

from cart.models import Cart
from checkout.models import CheckoutSession
from tenants.models import Tenant
from users.models import User

from .models import Order, OrderEvent


class OrderStateMachineTests(SimpleTestCase):
    def test_order_follows_fulfillment_state_machine(self):
        order = Order(status=Order.Status.PENDING)

        self.assertTrue(can_proceed(order.confirm))
        order.confirm()
        self.assertEqual(order.status, Order.Status.CONFIRMED)

        self.assertTrue(can_proceed(order.mark_processing))
        order.mark_processing()
        self.assertEqual(order.status, Order.Status.PROCESSING)

        self.assertTrue(can_proceed(order.mark_shipped))
        order.mark_shipped()
        self.assertEqual(order.status, Order.Status.SHIPPED)

        self.assertTrue(can_proceed(order.mark_delivered))
        order.mark_delivered()
        self.assertEqual(order.status, Order.Status.DELIVERED)

    def test_order_can_be_cancelled_only_while_pending(self):
        order = Order(status=Order.Status.PENDING)

        self.assertTrue(can_proceed(order.cancel))
        order.cancel()
        self.assertEqual(order.status, Order.Status.CANCELLED)

        with self.assertRaises(TransitionNotAllowed):
            order.confirm()

    def test_order_rejects_out_of_order_transitions(self):
        order = Order(status=Order.Status.PENDING)

        with self.assertRaises(TransitionNotAllowed):
            order.mark_shipped()

        order.confirm()
        with self.assertRaises(TransitionNotAllowed):
            order.mark_delivered()


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

    def test_order_transition_creates_audit_event(self):
        order = self._create_order()

        order.confirm()
        order.save(update_fields=['status', 'updated_at'])

        event = order.events.get()
        self.assertEqual(event.from_status, Order.Status.PENDING)
        self.assertEqual(event.to_status, Order.Status.CONFIRMED)
        self.assertEqual(event.transition, 'confirm')
        self.assertEqual(event.tenant, self.tenant)

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
