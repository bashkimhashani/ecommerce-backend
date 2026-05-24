from django.db import models

from tenants.mixins import TenantModel


class AIReport(TenantModel):
    class ReportType(models.TextChoices):
        NIGHTLY_SALES = 'nightly_sales', 'Nightly sales'

    report_type = models.CharField(
        max_length=50,
        choices=ReportType.choices,
        db_index=True,
    )
    content = models.TextField()
    generated_at = models.DateTimeField(auto_now_add=True, db_index=True)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-generated_at']
        indexes = [
            models.Index(fields=['tenant', 'report_type', '-generated_at']),
        ]

    def __str__(self):
        return f'{self.report_type} report for tenant {self.tenant_id}'
