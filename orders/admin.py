from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    raw_id_fields = ('product_variant',)
    readonly_fields = ('line_total', 'created_at')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_number',
        'user',
        'status',
        'total_amount',
        'tenant',
        'created_at',
    )
    list_filter = ('status', 'tenant', 'created_at')
    search_fields = ('order_number', 'user__email')
    raw_id_fields = ('user', 'checkout_session')
    readonly_fields = ('created_at', 'updated_at')
    inlines = (OrderItemInline,)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        'order',
        'product_name',
        'variant_label',
        'quantity',
        'unit_price',
        'line_total',
    )
    list_filter = ('tenant', 'created_at')
    raw_id_fields = ('order', 'product_variant')
