from django.contrib import admin

from .models import CheckoutSession


@admin.register(CheckoutSession)
class CheckoutSessionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'cart',
        'status',
        'tenant',
        'created_at',
    )
    list_filter = ('status', 'tenant', 'created_at')
    search_fields = (
        'user__email',
        'idempotency_key',
        'cart__session_key',
    )
    raw_id_fields = ('user', 'cart')
    readonly_fields = ('created_at', 'updated_at')
