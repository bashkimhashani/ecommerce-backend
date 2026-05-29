from django.utils.text import slugify
from rest_framework import serializers

from vendor.models import VendorProfile

from .models import Brand, Category, Product, ProductImage, ProductVariant


class CategoryTreeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "icon_url",
            "is_active",
            "children",
        ]

    def get_children(self, obj):
        children = obj.get_children().filter(is_active=True)
        serializer = self.__class__(
            children,
            many=True,
            context=self.context,
        )
        return serializer.data


class ProductListSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(
        source="base_price",
        max_digits=10,
        decimal_places=2,
    )
    vendor = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "price",
            "vendor",
            "thumbnail",
            "avg_rating",
        ]

    def get_vendor(self, obj):
        if obj.vendor_id is None:
            return None

        serializer = VendorSummarySerializer(obj.vendor)
        return serializer.data

    def get_thumbnail(self, obj):
        primary_image = next(
            (image for image in obj.images.all() if image.is_primary),
            None,
        )
        if primary_image is None:
            primary_image = next(iter(obj.images.all()), None)
        if primary_image is None or not primary_image.thumbnail:
            return None

        request = self.context.get("request")
        thumbnail_url = primary_image.thumbnail.url
        if request:
            return request.build_absolute_uri(thumbnail_url)
        return thumbnail_url

    def get_avg_rating(self, obj):
        return getattr(obj, "avg_rating", None)


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = [
            "id",
            "image",
            "thumbnail",
            "medium",
            "large",
            "alt_text",
            "sort_order",
            "is_primary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "thumbnail",
            "medium",
            "large",
            "created_at",
            "updated_at",
        ]


class BrandSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = [
            "id",
            "name",
            "slug",
            "logo",
            "country_of_origin",
        ]


class CategorySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "icon_url",
        ]


class VendorSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorProfile
        fields = [
            "id",
            "store_name",
            "logo",
            "rating",
        ]


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "color",
            "storage",
            "ram",
            "variant_price",
            "stock_quantity",
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(
        source="base_price",
        max_digits=10,
        decimal_places=2,
    )
    brand = BrandSummarySerializer(read_only=True)
    category = CategorySummarySerializer(read_only=True)
    vendor = VendorSummarySerializer(read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    specs = serializers.JSONField(source="tech_specs")
    avg_rating = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "brand",
            "category",
            "vendor",
            "status",
            "price",
            "specs",
            "variants",
            "images",
            "avg_rating",
            "created_at",
            "updated_at",
        ]

    def get_avg_rating(self, obj):
        return getattr(obj, "avg_rating", None)


class ProductCreateSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(max_length=255, required=False, write_only=True)
    category_name = serializers.CharField(max_length=255, required=False, write_only=True)
    stock_quantity = serializers.IntegerField(min_value=0, required=False, write_only=True)
    color = serializers.CharField(max_length=100, required=False, allow_blank=True, write_only=True)
    storage = serializers.CharField(max_length=100, required=False, allow_blank=True, write_only=True)
    ram = serializers.CharField(max_length=100, required=False, allow_blank=True, write_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "brand",
            "category",
            "status",
            "base_price",
            "tech_specs",
            "brand_name",
            "category_name",
            "stock_quantity",
            "color",
            "storage",
            "ram",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        tenant = getattr(getattr(request, "user", None), "tenant", None)

        if tenant:
            self.fields["brand"].queryset = Brand.all_objects.filter(
                tenant=tenant,
            )
            self.fields["category"].queryset = Category.all_objects.filter(
                tenant=tenant,
            )
            self.fields["brand"].required = False
            self.fields["category"].required = False
        else:
            self.fields["brand"].queryset = Brand.all_objects.none()
            self.fields["category"].queryset = Category.all_objects.none()

    def validate(self, attrs):
        request = self.context.get("request")
        tenant = getattr(getattr(request, "user", None), "tenant", None)

        if tenant is None:
            raise serializers.ValidationError(
                "A tenant is required to create products.",
            )

        if not attrs.get("brand") and not attrs.get("brand_name"):
            attrs["brand_name"] = getattr(tenant, "name", "Vendor")
        if not attrs.get("category") and not attrs.get("category_name"):
            attrs["category_name"] = "General"

        slug = attrs.get("slug")
        sku = attrs.get("sku")
        errors = {}

        slug_exists = Product.all_objects.filter(
            tenant=tenant,
            slug=slug,
        )
        sku_exists = Product.all_objects.filter(
            tenant=tenant,
            sku=sku,
        )

        if self.instance:
            slug_exists = slug_exists.exclude(id=self.instance.id)
            sku_exists = sku_exists.exclude(id=self.instance.id)

        if slug and slug_exists.exists():
            errors["slug"] = "A product with this slug already exists."

        if sku and sku_exists.exists():
            errors["sku"] = "A product with this SKU already exists."

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def create(self, validated_data):
        tenant = self.context["request"].user.tenant
        brand_name = validated_data.pop("brand_name", "")
        category_name = validated_data.pop("category_name", "")
        stock_quantity = validated_data.pop("stock_quantity", 0)
        color = validated_data.pop("color", "")
        storage = validated_data.pop("storage", "")
        ram = validated_data.pop("ram", "")

        if not validated_data.get("brand"):
            validated_data["brand"] = self.get_or_create_brand(tenant, brand_name)
        if not validated_data.get("category"):
            validated_data["category"] = self.get_or_create_category(tenant, category_name)

        product = super().create(validated_data)
        ProductVariant.objects.create(
            tenant=tenant,
            product=product,
            variant_price=product.base_price,
            stock_quantity=stock_quantity,
            color=color,
            storage=storage,
            ram=ram,
        )
        return product

    def get_or_create_brand(self, tenant, name):
        name = name.strip() or tenant.name
        slug = slugify(name)[:255] or f"brand-{tenant.id}"
        brand, _created = Brand.all_objects.get_or_create(
            tenant=tenant,
            slug=slug,
            defaults={"name": name},
        )
        return brand

    def get_or_create_category(self, tenant, name):
        name = name.strip() or "General"
        slug = slugify(name)[:255] or "general"
        category, _created = Category.all_objects.get_or_create(
            tenant=tenant,
            slug=slug,
            defaults={"name": name, "is_active": True},
        )
        return category


class ProductImageBulkUpdateItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sort_order = serializers.IntegerField(min_value=0)
    alt_text = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
    )
    is_primary = serializers.BooleanField(required=False)


class ProductImageBulkUpdateSerializer(serializers.Serializer):
    images = ProductImageBulkUpdateItemSerializer(
        many=True,
        allow_empty=False,
    )
