from celery.result import AsyncResult
from django.core.cache import cache
from django.db.models import F

from ai.models import AIReport
from inventory.models import Inventory

from .models import VendorProfile
from .order_reports import (
    serialize_decimal,
    vendor_order_summary_rows,
    vendor_order_totals,
)
from .tasks import export_vendor_orders_csv


class VendorService:
    @staticmethod
    def get_vendor_for_user(user):
        return VendorProfile.objects.filter(
            user=user,
            tenant=user.tenant,
        ).first()

    @classmethod
    def get_dashboard_summary(cls, user):
        vendor = cls.get_vendor_for_user(user)
        if vendor is None:
            return None

        inventory = cls.get_vendor_inventory(vendor)
        low_stock_items = inventory.filter(
            quantity__lt=F('low_stock_threshold'),
        )
        order_totals = vendor_order_totals(vendor)

        return {
            'order_count': order_totals['order_count'],
            'revenue': serialize_decimal(order_totals['revenue']),
            'low_stock_alerts': low_stock_items.count(),
            'low_stock_items': low_stock_items,
        }

    @staticmethod
    def get_latest_sales_report(user):
        return AIReport.all_objects.filter(
            tenant=user.tenant,
            report_type=AIReport.ReportType.NIGHTLY_SALES,
        ).order_by('-generated_at').first()

    @staticmethod
    def get_vendor_inventory(vendor):
        return Inventory.all_objects.filter(
            tenant=vendor.tenant,
            vendor=vendor,
        ).select_related(
            'product_variant',
            'product_variant__product',
        )

    @classmethod
    def list_inventory_for_user(cls, user):
        vendor = cls.get_vendor_for_user(user)
        if vendor is None:
            return None

        return cls.get_vendor_inventory(vendor).order_by(
            'product_variant__product__name',
            'id',
        )

    @classmethod
    def get_inventory_item_for_user(cls, user, inventory_id):
        vendor = cls.get_vendor_for_user(user)
        if vendor is None:
            return None, None

        inventory = cls.get_vendor_inventory(vendor).filter(id=inventory_id).first()
        return vendor, inventory

    @staticmethod
    def get_order_summary(vendor):
        cache_key = f'vendor_order_summary_{vendor.id}'
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        result = vendor_order_summary_rows(vendor)
        cache.set(cache_key, result, 300)
        return result

    @staticmethod
    def queue_order_export(user, vendor):
        task = export_vendor_orders_csv.delay(vendor.id, user.id)
        cache.set(f'vendor_export_task_{user.id}', task.id, 3600)
        return {
            'task_id': task.id,
            'status': 'queued',
            'message': 'CSV export has been queued',
            'poll_url': f'/api/v1/vendor/export/status/?task_id={task.id}',
        }

    @staticmethod
    def get_export_status(task_id):
        task = AsyncResult(task_id)
        response_data = {
            'task_id': task_id,
            'status': task.state,
        }

        if task.state == 'SUCCESS':
            response_data['result'] = task.result
            response_data['download_url'] = task.result.get('download_url')
        elif task.state == 'FAILURE':
            response_data['error'] = str(task.info)

        return response_data
