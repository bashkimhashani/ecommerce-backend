from django.contrib import admin

from .models import Brand, Category, Product, ProductImage, ProductVariant


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'country_of_origin', 'tenant', 'created_at')
    search_fields = ('name', 'slug', 'country_of_origin')
    list_filter = ('country_of_origin', 'tenant')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'tenant', 'created_at')
    search_fields = ('name', 'slug')
    list_filter = ('tenant',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'brand', 'category', 'status', 'base_price', 'tenant')
    search_fields = ('name', 'slug', 'sku', 'brand__name', 'category__name')
    list_filter = ('status', 'brand', 'category', 'tenant')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('product', 'color', 'storage', 'ram', 'variant_price', 'stock_quantity', 'tenant')
    search_fields = ('product__name', 'product__sku', 'color', 'storage', 'ram')
    list_filter = ('color', 'storage', 'ram', 'tenant')


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'alt_text', 'sort_order', 'is_primary', 'tenant')
    search_fields = ('product__name', 'product__sku', 'alt_text')
    list_filter = ('is_primary', 'tenant')
