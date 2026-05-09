from rest_framework import serializers

from .models import Category, ProductImage


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


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = [
            'id',
            'image',
            'alt_text',
            'sort_order',
            'is_primary',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
        ]
