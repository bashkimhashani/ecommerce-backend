from django.db import models

from tenants.mixins import TenantModel


class EmailLog(TenantModel):
    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    task_name = models.CharField(max_length=255, db_index=True)
    recipient = models.EmailField(blank=True)
    subject = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        db_index=True,
    )
    related_object_id = models.CharField(max_length=64, blank=True)
    message = models.TextField(blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["tenant", "status"],
                name="notificatio_tenant__16ab8d_idx",
            ),
            models.Index(
                fields=["task_name", "status"],
                name="notificatio_task_na_4d5b17_idx",
            ),
        ]

    def __str__(self):
        return f"{self.task_name} -> {self.recipient} ({self.status})"


class FailedTask(TenantModel):
    task_name = models.CharField(max_length=255, db_index=True)
    arguments = models.JSONField(default=dict, blank=True)
    exception = models.TextField()
    traceback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["task_name"],
                name="notificatio_task_na_b4caca_idx",
            ),
            models.Index(
                fields=["tenant", "task_name"],
                name="notificatio_tenant__6d4647_idx",
            ),
        ]

    def __str__(self):
        return f"{self.task_name} failed at {self.created_at}"
