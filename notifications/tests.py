from decimal import Decimal
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from cart.models import Cart, CartItem
from checkout.models import CheckoutSession
from checkout.services import OrderCreationService
from orders.models import Order
from tenants.models import Tenant

from .models import EmailLog
from .tasks import (
    ORDER_CONFIRMATION_TASK,
    PASSWORD_RESET_TASK,
    send_order_confirmation,
    send_password_reset_email,
)


User = get_user_model()


class PasswordResetEmailQueueingTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store',
            domain='acme.example.com',
            plan='basic',
        )
        self.user = User.objects.create_user(
            email='customer@example.com',
            password='OldStrongPass123',
            first_name='Customer',
            last_name='User',
            role='customer',
            tenant=self.tenant,
        )

    def test_password_reset_endpoint_queues_notification_task(self):
        with patch('users.views.send_password_reset_email.delay') as delay:
            response = self.client.post(
                reverse('password-reset'),
                {'email': self.user.email},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        delay.assert_called_once()
        user_id, token = delay.call_args.args
        self.assertEqual(user_id, self.user.id)
        self.assertTrue(default_token_generator.check_token(self.user, token))


class TransactionalEmailQueueingTests(TestCase):
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

    @patch('checkout.services.send_order_confirmation.delay')
    def test_order_creation_queues_confirmation_email_after_commit(
        self,
        delay,
    ):
        checkout_session = self._create_checkout_session_with_cart_item()

        with self.captureOnCommitCallbacks(execute=True):
            order = OrderCreationService.create_from_checkout(checkout_session)

        delay.assert_called_once_with(order.pk)

    @patch('orders.models.send_order_shipped.delay')
    def test_shipped_transition_queues_shipped_email_after_commit(self, delay):
        order = self._create_order(status=Order.Status.PROCESSING)

        with self.captureOnCommitCallbacks(execute=True):
            order.mark_shipped()
            order.save(update_fields=['status', 'updated_at'])

        delay.assert_called_once_with(order.pk)

    def _create_checkout_session_with_cart_item(self):
        cart = Cart.objects.create(user=self.user, tenant=self.tenant)
        product_variant = self._create_product_variant()
        CartItem.objects.create(
            cart=cart,
            product_variant=product_variant,
            quantity=1,
            unit_price=product_variant.variant_price,
            tenant=self.tenant,
        )
        return CheckoutSession.objects.create(
            user=self.user,
            cart=cart,
            idempotency_key='checkout-key-123',
            shipping_address=self._shipping_address(),
            status=CheckoutSession.Status.READY,
            tenant=self.tenant,
        )

    def _create_order(self, status=Order.Status.PENDING):
        cart = Cart.objects.create(user=self.user, tenant=self.tenant)
        checkout_session = CheckoutSession.objects.create(
            user=self.user,
            cart=cart,
            idempotency_key=f'checkout-key-{status}',
            shipping_address=self._shipping_address(),
            status=CheckoutSession.Status.READY,
            tenant=self.tenant,
        )
        return Order.objects.create(
            user=self.user,
            checkout_session=checkout_session,
            shipping_address=self._shipping_address(),
            status=status,
            subtotal=Decimal('99.00'),
            total_amount=Decimal('99.00'),
            tenant=self.tenant,
        )

    def _create_product_variant(self):
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
            base_price=Decimal('999.00'),
            tenant=self.tenant,
        )
        return ProductVariant.objects.create(
            product=product,
            color='Black',
            storage='256GB',
            ram='8GB',
            variant_price=Decimal('999.00'),
            stock_quantity=5,
            tenant=self.tenant,
        )

    def _shipping_address(self):
        return {
            'full_name': 'Customer User',
            'line1': 'Main street 1',
            'line2': 'Apartment 4',
            'city': 'Prishtina',
            'postal_code': '10000',
            'country': 'Kosovo',
        }


class EmailLogCreationTests(TestCase):
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

    @patch('notifications.tasks.send_mail')
    def test_password_reset_task_creates_sent_email_log(self, send_mail):
        result = send_password_reset_email.run(self.user.id, 'reset-token')

        self.assertEqual(result['status'], EmailLog.Status.SENT)
        send_mail.assert_called_once()
        email_log = EmailLog.all_objects.get()
        self.assertEqual(email_log.task_name, PASSWORD_RESET_TASK)
        self.assertEqual(email_log.recipient, self.user.email)
        self.assertEqual(email_log.subject, 'Reset your password')
        self.assertEqual(email_log.status, EmailLog.Status.SENT)
        self.assertEqual(email_log.related_object_id, str(self.user.id))
        self.assertEqual(email_log.tenant, self.tenant)
        self.assertIn('Reset password', email_log.message)

    @patch('notifications.tasks.send_mail')
    def test_password_reset_task_creates_failed_email_log(self, send_mail):
        send_mail.side_effect = RuntimeError('SMTP is unavailable')

        with self.assertRaises(RuntimeError):
            send_password_reset_email.run(self.user.id, 'reset-token')

        email_log = EmailLog.all_objects.get()
        self.assertEqual(email_log.task_name, PASSWORD_RESET_TASK)
        self.assertEqual(email_log.status, EmailLog.Status.FAILED)
        self.assertEqual(email_log.error, 'SMTP is unavailable')
        self.assertEqual(email_log.recipient, self.user.email)

    @patch('notifications.tasks.send_mail')
    def test_order_confirmation_task_creates_sent_email_log(self, send_mail):
        order = self._create_order()

        result = send_order_confirmation.run(order.id)

        self.assertEqual(result['status'], EmailLog.Status.SENT)
        send_mail.assert_called_once()
        email_log = EmailLog.all_objects.get()
        self.assertEqual(email_log.task_name, ORDER_CONFIRMATION_TASK)
        self.assertEqual(email_log.recipient, self.user.email)
        self.assertEqual(email_log.status, EmailLog.Status.SENT)
        self.assertEqual(email_log.related_object_id, str(order.id))
        self.assertEqual(email_log.tenant, self.tenant)
        self.assertIn(order.order_number, email_log.subject)

    def _create_order(self):
        cart = Cart.objects.create(user=self.user, tenant=self.tenant)
        checkout_session = CheckoutSession.objects.create(
            user=self.user,
            cart=cart,
            idempotency_key='checkout-key-log',
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
            shipping_address=checkout_session.shipping_address,
            subtotal=Decimal('99.00'),
            total_amount=Decimal('99.00'),
            tenant=self.tenant,
        )
