import django_filters

from .models import Product


class ProductFilter(django_filters.FilterSet):
    min_price = django_filters.NumberFilter(
        field_name='base_price',
        lookup_expr='gte',
    )
    max_price = django_filters.NumberFilter(
        field_name='base_price',
        lookup_expr='lte',
    )
    brand = django_filters.CharFilter(field_name='brand__slug')
    category = django_filters.CharFilter(field_name='category__slug')
    is_in_stock = django_filters.BooleanFilter(method='filter_is_in_stock')

    class Meta:
        model = Product
        fields = [
            'min_price',
            'max_price',
            'brand',
            'category',
            'is_in_stock',
        ]

    def filter_is_in_stock(self, queryset, name, value):
        lookup = {'variants__stock_quantity__gt': 0}
        if value:
            return queryset.filter(**lookup).distinct()
        return queryset.exclude(**lookup).distinct()
