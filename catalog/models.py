from django.db import models
from mptt.managers import TreeManager
from mptt.models import MPTTModel, TreeForeignKey

from tenants.middleware import get_current_tenant
from tenants.mixins import TenantModel


class TenantAwareTreeManager(TreeManager):
    def get_queryset(self):
        tenant = get_current_tenant()
        qs = super().get_queryset()
        if tenant:
            return qs.filter(tenant=tenant)
        return qs


class Brand(TenantModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    logo = models.ImageField(upload_to="brands/logos/", null=True, blank=True)
    country_of_origin = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                name="unique_brand_slug_per_tenant",
            ),
        ]

    def __str__(self):
        return self.name


class Category(MPTTModel, TenantModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    parent = TreeForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    icon_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantAwareTreeManager()

    class MPTTMeta:
        order_insertion_by = ["name"]

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["tree_id", "lft"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                name="unique_category_slug_per_tenant",
            ),
        ]

    def __str__(self):
        return self.name


class Product(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, db_index=True)
    sku = models.CharField(max_length=100, db_index=True)
    description = models.TextField(blank=True, default="")
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="products",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
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
        ordering = ["name"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "category"]),
            models.Index(fields=["tenant", "brand"]),
            models.Index(fields=["tenant", "vendor"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                name="unique_product_slug_per_tenant",
            ),
            models.UniqueConstraint(
                fields=["tenant", "sku"],
                name="unique_product_sku_per_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"


class ProductVariant(TenantModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    color = models.CharField(max_length=100, blank=True)
    storage = models.CharField(max_length=100, blank=True)
    ram = models.CharField("RAM", max_length=100, blank=True)
    variant_price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product__name", "color", "storage", "ram"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "product", "color", "storage", "ram"],
                name="unique_product_variant_per_tenant",
            ),
        ]

    def __str__(self):
        options = ", ".join(
            value for value in [self.color, self.storage, self.ram] if value
        )
        return f"{self.product.name} - {options}" if options else self.product.name


class ProductImage(TenantModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="products/images/")
    thumbnail = models.ImageField(
        upload_to="products/images/generated/",
        null=True,
        blank=True,
        editable=False,
    )
    medium = models.ImageField(
        upload_to="products/images/generated/",
        null=True,
        blank=True,
        editable=False,
    )
    large = models.ImageField(
        upload_to="products/images/generated/",
        null=True,
        blank=True,
        editable=False,
    )
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["tenant", "product", "sort_order"]),
            models.Index(fields=["tenant", "product", "is_primary"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "product", "sort_order"],
                name="unique_product_image_sort_order_per_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} image {self.sort_order}"
