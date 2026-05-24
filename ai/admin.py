from django.contrib import admin

from .models import AIReport


@admin.register(AIReport)
class AIReportAdmin(admin.ModelAdmin):
    list_display = [
        'tenant',
        'report_type',
        'generated_at',
        'prompt_tokens',
        'completion_tokens',
    ]
    list_filter = ['report_type', 'tenant']
    search_fields = ['content', 'tenant__name']
