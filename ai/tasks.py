from celery import shared_task

from tenants.models import Tenant

from .models import AIReport
from .services import AIReportGenerator, SalesAggregator


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def generate_nightly_report(self, tenant_id=None):
    if tenant_id is None:
        report_ids = []
        for tenant in Tenant.objects.filter(is_active=True):
            report_ids.append(generate_nightly_report.delay(tenant.id).id)
        return report_ids

    tenant = Tenant.objects.get(pk=tenant_id)
    summary = SalesAggregator().get_period_summary(tenant, days=30)
    generated = AIReportGenerator().generate(summary)
    report = AIReport.all_objects.create(
        tenant=tenant,
        report_type=AIReport.ReportType.NIGHTLY_SALES,
        content=generated['content'],
        prompt_tokens=generated.get('prompt_tokens', 0),
        completion_tokens=generated.get('completion_tokens', 0),
    )
    return report.id
