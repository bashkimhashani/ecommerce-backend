from rest_framework import serializers

from .models import Category


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
