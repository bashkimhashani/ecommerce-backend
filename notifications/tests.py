from types import SimpleNamespace

from django.test import TestCase

from tenants.models import Tenant

from .models import FailedTask
from .signals import log_exhausted_task


class FailedTaskModelTests(TestCase):
    def test_failed_task_stores_failure_details(self):
        tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store-notifications',
            domain='notifications.acme.example.com',
            plan='basic',
        )

        failed_task = FailedTask.all_objects.create(
            tenant=tenant,
            task_name='notifications.tasks.send_order_confirmation',
            arguments={
                'args': [123],
                'kwargs': {'force': True},
            },
            exception='SMTP timeout',
            traceback='Traceback details',
        )

        failed_task.refresh_from_db()

        self.assertEqual(
            failed_task.task_name,
            'notifications.tasks.send_order_confirmation',
        )
        self.assertEqual(failed_task.arguments['args'], [123])
        self.assertEqual(failed_task.arguments['kwargs'], {'force': True})
        self.assertEqual(failed_task.exception, 'SMTP timeout')
        self.assertEqual(failed_task.traceback, 'Traceback details')
        self.assertEqual(failed_task.tenant, tenant)


class FailedTaskSignalTests(TestCase):
    def task_sender(self, retries, max_retries=3):
        return SimpleNamespace(
            name='notifications.tasks.send_order_confirmation',
            max_retries=max_retries,
            request=SimpleNamespace(retries=retries),
        )

    def test_signal_skips_task_before_retries_are_exhausted(self):
        log_exhausted_task(
            sender=self.task_sender(retries=1),
            exception=RuntimeError('Temporary SMTP failure'),
            args=(123,),
            kwargs={'force': True},
            einfo='Traceback details',
        )

        self.assertFalse(FailedTask.all_objects.exists())

    def test_signal_routes_exhausted_task_to_failed_task(self):
        log_exhausted_task(
            sender=self.task_sender(retries=3),
            exception=RuntimeError('SMTP offline'),
            args=(123, object()),
            kwargs={'force': True},
            einfo='Traceback details',
        )

        failed_task = FailedTask.all_objects.get()

        self.assertEqual(
            failed_task.task_name,
            'notifications.tasks.send_order_confirmation',
        )
        self.assertEqual(failed_task.arguments['args'][0], 123)
        self.assertIn('object object', failed_task.arguments['args'][1])
        self.assertEqual(failed_task.arguments['kwargs'], {'force': True})
        self.assertEqual(failed_task.exception, 'SMTP offline')
        self.assertEqual(failed_task.traceback, 'Traceback details')
