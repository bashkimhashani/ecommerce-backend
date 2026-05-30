from drf_spectacular.utils import OpenApiTypes, extend_schema_field
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

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
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

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_vendor(self, obj):
        if obj.vendor_id is None:
            return None

        serializer = VendorSummarySerializer(obj.vendor)
        return serializer.data

    @extend_schema_field(OpenApiTypes.URI)
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

    @extend_schema_field(OpenApiTypes.FLOAT)
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

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_avg_rating(self, obj):
        return getattr(obj, "avg_rating", None)


class ProductCreateSerializer(serializers.ModelSerializer):
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
