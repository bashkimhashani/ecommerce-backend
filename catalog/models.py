from django.db import models

from tenants.mixins import TenantModel


class Brand(TenantModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    logo = models.ImageField(upload_to='brands/logos/', null=True, blank=True)
    country_of_origin = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'slug'],
                name='unique_brand_slug_per_tenant',
            ),
        ]

    def __str__(self):
        return self.name


class Category(TenantModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'slug'],
                name='unique_category_slug_per_tenant',
            ),
        ]

    def __str__(self):
        return self.name


class Product(TenantModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ACTIVE = 'active', 'Active'
        ARCHIVED = 'archived', 'Archived'

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    sku = models.CharField(max_length=100)
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name='products',
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    tech_specs = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'category']),
            models.Index(fields=['tenant', 'brand']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'slug'],
                name='unique_product_slug_per_tenant',
            ),
            models.UniqueConstraint(
                fields=['tenant', 'sku'],
                name='unique_product_sku_per_tenant',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.sku})'
