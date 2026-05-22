from django.db import models


class RequestLog(models.Model):
    method = models.CharField(max_length=10)
    path = models.TextField()
    status_code = models.PositiveSmallIntegerField()
    response_time_ms = models.DecimalField(max_digits=10, decimal_places=2)
    tenant_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['status_code']),
        ]

    def __str__(self):
        return (
            f'{self.method} {self.path} '
            f'{self.status_code} {self.response_time_ms}ms'
        )
