from rest_framework import serializers

from .models import Category, Product, ProductImage


class CategoryTreeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id',
            'name',
            'slug',
            'icon_url',
            'is_active',
            'children',
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
        source='base_price',
        max_digits=10,
        decimal_places=2,
    )
    thumbnail = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'slug',
            'price',
            'thumbnail',
            'avg_rating',
        ]

    def get_thumbnail(self, obj):
        primary_image = next(
            (
                image for image in obj.images.all()
                if image.is_primary
            ),
            None,
        )
        if primary_image is None:
            primary_image = next(iter(obj.images.all()), None)
        if primary_image is None or not primary_image.thumbnail:
            return None

        request = self.context.get('request')
        thumbnail_url = primary_image.thumbnail.url
        if request:
            return request.build_absolute_uri(thumbnail_url)
        return thumbnail_url

    def get_avg_rating(self, obj):
        return getattr(obj, 'avg_rating', None)


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = [
            'id',
            'image',
            'thumbnail',
            'medium',
            'large',
            'alt_text',
            'sort_order',
            'is_primary',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'thumbnail',
            'medium',
            'large',
            'created_at',
            'updated_at',
        ]


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
