from django.test import TestCase

from tenants.models import Tenant

from .models import FailedTask


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
