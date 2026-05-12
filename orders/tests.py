from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django_fsm import TransitionNotAllowed, can_proceed

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
