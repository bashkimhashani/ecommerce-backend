from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from celery.exceptions import MaxRetriesExceededError
from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ai.tasks import generate_nightly_report
from cart.models import Cart, CartItem
from checkout.models import CheckoutSession
from checkout.services import OrderCreationService
from inventory.tasks import send_low_stock_alert
from orders.models import Order
from orders.tasks import send_order_status_email
from tenants.models import Tenant
from users.tasks import (
    send_email_verification_email,
    send_password_reset_email as send_user_password_reset_email,
)

from .models import EmailLog, FailedTask
from .signals import log_exhausted_task
from .tasks import (
    ORDER_CONFIRMATION_TASK,
    PASSWORD_RESET_TASK,
    send_order_confirmation,
    send_order_shipped,
    send_password_reset_email,
)

User = get_user_model()


class ExternalTaskRetryConfigurationTests(TestCase):
    def external_api_tasks(self):
        return [
            send_order_confirmation,
            send_order_shipped,
            send_password_reset_email,
            send_email_verification_email,
            send_user_password_reset_email,
            send_order_status_email,
            send_low_stock_alert,
            generate_nightly_report,
        ]

    def test_external_api_tasks_retry_exceptions_with_backoff(self):
        for task in self.external_api_tasks():
            with self.subTest(task=task.name):
                self.assertIn(Exception, task.autoretry_for)
                self.assertTrue(task.retry_backoff)


class PasswordResetEmailQueueingTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Acme Store",
            slug="acme-store",
            domain="acme.example.com",
            plan="basic",
        )
        self.user = User.objects.create_user(
            email="customer@example.com",
            password="OldStrongPass123",
            first_name="Customer",
            last_name="User",
            role="customer",
            tenant=self.tenant,
        )

    def test_password_reset_endpoint_queues_notification_task(self):
        with patch("users.services.send_password_reset_email.delay") as delay:
            response = self.client.post(
                reverse("password-reset"),
                {"email": self.user.email},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        delay.assert_called_once()
        user_id, token = delay.call_args.args
        self.assertEqual(user_id, self.user.id)
        self.assertTrue(default_token_generator.check_token(self.user, token))


class TransactionalEmailQueueingTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Acme Store",
            slug="acme-store",
            domain="acme.example.com",
            plan="basic",
        )
        self.user = User.objects.create_user(
            email="customer@example.com",
            password="StrongPass123",
            first_name="Customer",
            last_name="User",
            role="customer",
            tenant=self.tenant,
        )

    @patch("checkout.services.send_order_confirmation.delay")
    def test_order_creation_queues_confirmation_email_after_commit(
        self,
        delay,
    ):
        checkout_session = self._create_checkout_session_with_cart_item()

        with self.captureOnCommitCallbacks(execute=True):
            order = OrderCreationService.create_from_checkout(checkout_session)

        delay.assert_called_once_with(order.pk)

    @patch("orders.models.send_order_shipped.delay")
    def test_shipped_transition_queues_shipped_email_after_commit(self, delay):
        order = self._create_order(status=Order.Status.PROCESSING)

        with self.captureOnCommitCallbacks(execute=True):
            order.mark_shipped()
            order.save(update_fields=["status", "updated_at"])

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
            idempotency_key="checkout-key-123",
            shipping_address=self._shipping_address(),
            status=CheckoutSession.Status.READY,
            tenant=self.tenant,
        )

    def _create_order(self, status=Order.Status.PENDING):
        cart = Cart.objects.create(user=self.user, tenant=self.tenant)
        checkout_session = CheckoutSession.objects.create(
            user=self.user,
            cart=cart,
            idempotency_key=f"checkout-key-{status}",
            shipping_address=self._shipping_address(),
            status=CheckoutSession.Status.READY,
            tenant=self.tenant,
        )
        return Order.objects.create(
            user=self.user,
            checkout_session=checkout_session,
            shipping_address=self._shipping_address(),
            status=status,
            subtotal=Decimal("99.00"),
            total_amount=Decimal("99.00"),
            tenant=self.tenant,
        )

    def _create_product_variant(self):
        Brand = apps.get_model("catalog", "Brand")
        Category = apps.get_model("catalog", "Category")
        Product = apps.get_model("catalog", "Product")
        ProductVariant = apps.get_model("catalog", "ProductVariant")

        brand = Brand.objects.create(
            name="Acme",
            slug="acme",
            tenant=self.tenant,
        )
        category = Category.objects.create(
            name="Phones",
            slug="phones",
            tenant=self.tenant,
        )
        product = Product.objects.create(
            name="Phone Pro",
            slug="phone-pro",
            sku="PHONE-PRO",
            brand=brand,
            category=category,
            status="active",
            base_price=Decimal("999.00"),
            tenant=self.tenant,
        )
        return ProductVariant.objects.create(
            product=product,
            color="Black",
            storage="256GB",
            ram="8GB",
            variant_price=Decimal("999.00"),
            stock_quantity=5,
            tenant=self.tenant,
        )

    def _shipping_address(self):
        return {
            "full_name": "Customer User",
            "line1": "Main street 1",
            "line2": "Apartment 4",
            "city": "Prishtina",
            "postal_code": "10000",
            "country": "Kosovo",
        }


class EmailLogCreationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Acme Store",
            slug="acme-store",
            domain="acme.example.com",
            plan="basic",
        )
        self.user = User.objects.create_user(
            email="customer@example.com",
            password="StrongPass123",
            first_name="Customer",
            last_name="User",
            role="customer",
            tenant=self.tenant,
        )

    @patch("notifications.tasks.send_mail")
    def test_password_reset_task_creates_sent_email_log(self, send_mail):
        result = send_password_reset_email.run(self.user.id, "reset-token")

        self.assertEqual(result["status"], EmailLog.Status.SENT)
        send_mail.assert_called_once()
        email_log = EmailLog.all_objects.get()
        self.assertEqual(email_log.task_name, PASSWORD_RESET_TASK)
        self.assertEqual(email_log.recipient, self.user.email)
        self.assertEqual(email_log.subject, "Reset your password")
        self.assertEqual(email_log.status, EmailLog.Status.SENT)
        self.assertEqual(email_log.related_object_id, str(self.user.id))
        self.assertEqual(email_log.tenant, self.tenant)
        self.assertIn("Reset password", email_log.message)

    @patch("notifications.tasks.send_mail")
    def test_password_reset_task_creates_failed_email_log(self, send_mail):
        send_mail.side_effect = RuntimeError("SMTP is unavailable")

        with self.assertRaises(RuntimeError):
            send_password_reset_email.run(self.user.id, "reset-token")

        email_log = EmailLog.all_objects.get()
        self.assertEqual(email_log.task_name, PASSWORD_RESET_TASK)
        self.assertEqual(email_log.status, EmailLog.Status.FAILED)
        self.assertEqual(email_log.error, "SMTP is unavailable")
        self.assertEqual(email_log.recipient, self.user.email)

    @patch("notifications.tasks.send_mail")
    def test_order_confirmation_task_creates_sent_email_log(self, send_mail):
        order = self._create_order()

        result = send_order_confirmation.run(order.id)

        self.assertEqual(result["status"], EmailLog.Status.SENT)
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
            idempotency_key="checkout-key-log",
            shipping_address={
                "full_name": "Customer User",
                "line1": "Main street 1",
                "city": "Prishtina",
                "postal_code": "10000",
                "country": "Kosovo",
            },
            status=CheckoutSession.Status.READY,
            tenant=self.tenant,
        )
        return Order.objects.create(
            user=self.user,
            checkout_session=checkout_session,
            shipping_address=checkout_session.shipping_address,
            subtotal=Decimal("99.00"),
            total_amount=Decimal("99.00"),
            tenant=self.tenant,
        )


class FailedTaskModelTests(TestCase):
    def test_failed_task_stores_failure_details(self):
        tenant = Tenant.objects.create(
            name="Acme Store",
            slug="acme-store-notifications",
            domain="notifications.acme.example.com",
            plan="basic",
        )

        failed_task = FailedTask.all_objects.create(
            tenant=tenant,
            task_name="notifications.tasks.send_order_confirmation",
            arguments={
                "args": [123],
                "kwargs": {"force": True},
            },
            exception="SMTP timeout",
            traceback="Traceback details",
        )

        failed_task.refresh_from_db()

        self.assertEqual(
            failed_task.task_name,
            "notifications.tasks.send_order_confirmation",
        )
        self.assertEqual(failed_task.arguments["args"], [123])
        self.assertEqual(failed_task.arguments["kwargs"], {"force": True})
        self.assertEqual(failed_task.exception, "SMTP timeout")
        self.assertEqual(failed_task.traceback, "Traceback details")
        self.assertEqual(failed_task.tenant, tenant)


class FailedTaskSignalTests(TestCase):
    def task_sender(self, retries, max_retries=3):
        return SimpleNamespace(
            name="notifications.tasks.send_order_confirmation",
            max_retries=max_retries,
            request=SimpleNamespace(retries=retries),
        )

    def test_signal_skips_task_before_retries_are_exhausted(self):
        log_exhausted_task(
            sender=self.task_sender(retries=1),
            exception=RuntimeError("Temporary SMTP failure"),
            args=(123,),
            kwargs={"force": True},
            einfo="Traceback details",
        )

        self.assertFalse(FailedTask.all_objects.exists())

    def test_signal_routes_exhausted_task_to_failed_task(self):
        log_exhausted_task(
            sender=self.task_sender(retries=3),
            exception=RuntimeError("SMTP offline"),
            args=(123, object()),
            kwargs={"force": True},
            einfo="Traceback details",
        )

        failed_task = FailedTask.all_objects.get()

        self.assertEqual(
            failed_task.task_name,
            "notifications.tasks.send_order_confirmation",
        )
        self.assertEqual(failed_task.arguments["args"][0], 123)
        self.assertIn("object object", failed_task.arguments["args"][1])
        self.assertEqual(failed_task.arguments["kwargs"], {"force": True})
        self.assertEqual(failed_task.exception, "SMTP offline")
        self.assertEqual(failed_task.traceback, "Traceback details")

    def test_signal_dead_letters_task_when_max_retries_are_exceeded(self):
        log_exhausted_task(
            sender=self.task_sender(retries=3),
            exception=MaxRetriesExceededError("max retries exceeded"),
            args=(456,),
            kwargs={"email": "customer@example.com"},
            einfo="Final traceback",
        )

        failed_task = FailedTask.all_objects.get()

        self.assertEqual(
            failed_task.task_name,
            "notifications.tasks.send_order_confirmation",
        )
        self.assertEqual(failed_task.arguments["args"], [456])
        self.assertEqual(
            failed_task.arguments["kwargs"],
            {"email": "customer@example.com"},
        )
        self.assertEqual(failed_task.exception, "max retries exceeded")
        self.assertEqual(failed_task.traceback, "Final traceback")
