from django.contrib import admin

from .models import Order, OrderEvent, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    raw_id_fields = ('product_variant',)
    readonly_fields = ('line_total', 'created_at')


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    readonly_fields = (
        'from_status',
        'to_status',
        'transition',
        'note',
        'metadata',
        'created_at',
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


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
    inlines = (OrderItemInline, OrderEventInline)


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


@admin.register(OrderEvent)
class OrderEventAdmin(admin.ModelAdmin):
    list_display = (
        'order',
        'from_status',
        'to_status',
        'transition',
        'tenant',
        'created_at',
    )
    list_filter = ('to_status', 'tenant', 'created_at')
    search_fields = ('order__order_number', 'transition')
    raw_id_fields = ('order',)
    readonly_fields = (
        'order',
        'from_status',
        'to_status',
        'transition',
        'note',
        'metadata',
        'tenant',
        'created_at',
    )

    def has_add_permission(self, request):
        return False
