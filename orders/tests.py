from django.test import SimpleTestCase
from django_fsm import TransitionNotAllowed, can_proceed

from .models import Order


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
