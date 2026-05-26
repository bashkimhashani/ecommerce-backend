from django.db import models

from tenants.mixins import TenantModel


class AIReport(TenantModel):
    class ReportType(models.TextChoices):
        NIGHTLY_SALES = "nightly_sales", "Nightly sales"

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
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["tenant", "report_type", "-generated_at"]),
        ]

    def __str__(self):
        return f"{self.report_type} report for tenant {self.tenant_id}"


class Conversation(TenantModel):
    session_id = models.CharField(max_length=120, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["tenant", "session_id"]),
            models.Index(fields=["session_id", "-updated_at"]),
        ]

    def __str__(self):
        return self.session_id


class ConversationMessage(TenantModel):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["tenant", "conversation", "created_at"]),
            models.Index(fields=["conversation", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.conversation_id and self.tenant_id is None:
            self.tenant = self.conversation.tenant
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.role}: {self.content[:80]}"
