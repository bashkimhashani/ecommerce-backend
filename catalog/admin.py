from django.contrib import admin

from .models import Brand, Category, Product


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'tenant', 'created_at')
    search_fields = ('name', 'slug')
    list_filter = ('tenant',)
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
