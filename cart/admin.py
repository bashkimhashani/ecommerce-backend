from django.contrib import admin

from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    autocomplete_fields = ("product_variant",)
    readonly_fields = ("line_total", "created_at", "updated_at")


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "session_key",
        "status",
        "tenant",
        "total_items",
        "created_at",
    )
    list_filter = ("status", "tenant", "created_at")
    search_fields = ("user__email", "session_key")
    readonly_fields = ("created_at", "updated_at", "total_items", "subtotal")
    inlines = (CartItemInline,)


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = (
        "cart",
        "product_variant",
        "quantity",
        "unit_price",
        "line_total",
        "tenant",
    )
    list_filter = ("tenant", "created_at")
    search_fields = (
        "cart__user__email",
        "cart__session_key",
        "product_variant__product__name",
        "product_variant__product__sku",
    )
    autocomplete_fields = ("cart", "product_variant")
    readonly_fields = ("line_total", "created_at", "updated_at")
