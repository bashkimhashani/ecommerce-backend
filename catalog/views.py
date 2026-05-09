from hashlib import md5

from django.core.cache import cache
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import transaction
from django.db.models import Count, Max, Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from users.permissions import IsVendorAdmin

from .filters import ProductFilter
from .models import Category, Product, ProductImage
from .pagination import ProductCursorPagination
from .serializers import (
    CategoryTreeSerializer,
    ProductCreateSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductImageBulkUpdateSerializer,
    ProductImageSerializer,
)


class VendorWritePermissionMixin:
    vendor_write_methods = set()

    def get_permissions(self):
        if self.request.method in self.vendor_write_methods:
            return [IsVendorAdmin()]
        return super().get_permissions()


class CategoryTreeView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=CategoryTreeSerializer(many=True),
        tags=['Catalog'],
    )
    def get(self, request):
        categories = Category.all_objects.filter(
            parent__isnull=True,
            is_active=True,
        )

        if request.user.is_authenticated and request.user.tenant_id:
            categories = categories.filter(tenant=request.user.tenant)

        categories = categories.order_by('tree_id', 'lft')
        serializer = CategoryTreeSerializer(categories, many=True)
        return Response(serializer.data)


class ProductListView(VendorWritePermissionMixin, APIView):
    permission_classes = [AllowAny]
    pagination_class = ProductCursorPagination
    cache_timeout = 300
    vendor_write_methods = {'POST'}

    def get_cache_key(self, request):
        tenant_id = getattr(getattr(request, 'user', None), 'tenant_id', None)
        tenant_scope = f'tenant:{tenant_id}' if tenant_id else 'tenant:public'
        query_hash = md5(
            request.META.get('QUERY_STRING', '').encode('utf-8'),
        ).hexdigest()
        return f'catalog:product-list:{tenant_scope}:{query_hash}'

    @extend_schema(
        responses=inline_serializer(
            name='PaginatedProductListResponse',
            fields={
                'next': serializers.URLField(allow_null=True),
                'previous': serializers.URLField(allow_null=True),
                'results': ProductListSerializer(many=True),
            },
        ),
        tags=['Catalog'],
    )
    def get(self, request):
        response_data = cache.get_or_set(
            self.get_cache_key(request),
            lambda: self.get_product_list_data(request),
            self.cache_timeout,
        )
        return Response(response_data)

    def get_product_list_data(self, request):
        product_images = ProductImage.all_objects.only(
            'id',
            'product_id',
            'thumbnail',
            'is_primary',
            'sort_order',
        ).order_by('-is_primary', 'sort_order', 'id')
        products = Product.all_objects.filter(
            status=Product.Status.ACTIVE,
        ).select_related(
            'brand',
            'category',
        ).prefetch_related(
            Prefetch('images', queryset=product_images),
        )

        if request.user.is_authenticated and request.user.tenant_id:
            products = products.filter(tenant_id=request.user.tenant_id)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(products, request, view=self)
        serializer = ProductListSerializer(
            page,
            many=True,
            context={'request': request},
        )
        return paginator.get_paginated_response(serializer.data).data

    @extend_schema(
        request=ProductCreateSerializer,
        responses={status.HTTP_201_CREATED: ProductDetailSerializer},
        tags=['Catalog'],
    )
    def post(self, request):
        serializer = ProductCreateSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        product = serializer.save(tenant=request.user.tenant)
        response_serializer = ProductDetailSerializer(
            product,
            context={'request': request},
        )
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )


class ProductSearchView(APIView):
    permission_classes = [AllowAny]
    pagination_class = ProductCursorPagination
    price_ranges = [
        {
            'key': 'under_500',
            'label': 'Under $500',
            'min': None,
            'max': 500,
            'filters': {'base_price__lt': 500},
        },
        {
            'key': '500_999',
            'label': '$500 - $999',
            'min': 500,
            'max': 999,
            'filters': {
                'base_price__gte': 500,
                'base_price__lt': 1000,
            },
        },
        {
            'key': '1000_1999',
            'label': '$1,000 - $1,999',
            'min': 1000,
            'max': 1999,
            'filters': {
                'base_price__gte': 1000,
                'base_price__lt': 2000,
            },
        },
        {
            'key': '2000_plus',
            'label': '$2,000+',
            'min': 2000,
            'max': None,
            'filters': {'base_price__gte': 2000},
        },
    ]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='q',
                type=str,
                required=False,
                description=(
                    'Search term for product name, SKU, brand, or category.'
                ),
            ),
        ],
        responses=inline_serializer(
            name='PaginatedProductSearchResponse',
            fields={
                'next': serializers.URLField(allow_null=True),
                'previous': serializers.URLField(allow_null=True),
                'results': ProductListSerializer(many=True),
                'facets': serializers.JSONField(),
            },
        ),
        tags=['Catalog'],
    )
    def get(self, request):
        product_images = ProductImage.all_objects.only(
            'id',
            'product_id',
            'thumbnail',
            'is_primary',
            'sort_order',
        ).order_by('-is_primary', 'sort_order', 'id')
        products = Product.all_objects.filter(
            status=Product.Status.ACTIVE,
        ).select_related(
            'brand',
            'category',
        ).prefetch_related(
            Prefetch('images', queryset=product_images),
        )

        if request.user.is_authenticated and request.user.tenant_id:
            products = products.filter(tenant_id=request.user.tenant_id)

        query = request.query_params.get('q', '').strip()
        if query:
            search_vector = (
                SearchVector('name', weight='A')
                + SearchVector('description', weight='B')
            )
            search_query = SearchQuery(query)
            products = products.annotate(
                search=search_vector,
                search_rank=SearchRank(search_vector, search_query),
            ).filter(
                search=search_query,
            ).order_by(
                '-search_rank',
                'id',
            )

        product_filter = ProductFilter(
            data=request.query_params,
            queryset=products,
        )
        if not product_filter.is_valid():
            raise ValidationError(product_filter.errors)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(
            product_filter.qs,
            request,
            view=self,
        )
        serializer = ProductListSerializer(
            page,
            many=True,
            context={'request': request},
        )
        response = paginator.get_paginated_response(serializer.data)
        response.data['facets'] = self.get_facets(products)
        return response

    def get_facets(self, products):
        brands = [
            {
                'name': brand['brand__name'],
                'slug': brand['brand__slug'],
                'count': brand['count'],
            }
            for brand in products.order_by().values(
                'brand__name',
                'brand__slug',
            ).annotate(
                count=Count('id'),
            ).order_by(
                'brand__name',
            )
        ]
        price_ranges = [
            {
                'key': price_range['key'],
                'label': price_range['label'],
                'min': price_range['min'],
                'max': price_range['max'],
                'count': products.filter(**price_range['filters']).count(),
            }
            for price_range in self.price_ranges
        ]

        return {
            'brands': brands,
            'price_ranges': price_ranges,
        }


class ProductDetailView(VendorWritePermissionMixin, APIView):
    permission_classes = [AllowAny]
    cache_timeout = 600
    vendor_write_methods = {'PUT', 'DELETE'}

    def get_cache_key(self, request, slug):
        tenant_id = getattr(getattr(request, 'user', None), 'tenant_id', None)
        tenant_scope = f'tenant:{tenant_id}' if tenant_id else 'tenant:public'
        return f'catalog:product-detail:{tenant_scope}:{slug}'

    @extend_schema(
        responses=ProductDetailSerializer,
        tags=['Catalog'],
    )
    def get(self, request, slug):
        response_data = cache.get_or_set(
            self.get_cache_key(request, slug),
            lambda: self.get_product_detail_data(request, slug),
            self.cache_timeout,
        )
        return Response(response_data)

    def get_product_detail_data(self, request, slug):
        products = Product.all_objects.filter(
            status=Product.Status.ACTIVE,
        ).select_related(
            'brand',
            'category',
        ).prefetch_related(
            'variants',
            'images',
        )

        if request.user.is_authenticated and request.user.tenant_id:
            products = products.filter(tenant_id=request.user.tenant_id)

        product = get_object_or_404(products, slug=slug)
        serializer = ProductDetailSerializer(
            product,
            context={'request': request},
        )
        return serializer.data

    @extend_schema(
        request=ProductCreateSerializer,
        responses=ProductDetailSerializer,
        tags=['Catalog'],
    )
    def put(self, request, slug):
        product = get_object_or_404(
            Product.all_objects,
            slug=slug,
            tenant_id=request.user.tenant_id,
        )
        serializer = ProductCreateSerializer(
            product,
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        product = serializer.save(tenant=request.user.tenant)
        response_serializer = ProductDetailSerializer(
            product,
            context={'request': request},
        )
        return Response(response_serializer.data)

    @extend_schema(
        responses={status.HTTP_204_NO_CONTENT: None},
        tags=['Catalog'],
    )
    def delete(self, request, slug):
        product = get_object_or_404(
            Product.all_objects.prefetch_related('images'),
            slug=slug,
            tenant_id=request.user.tenant_id,
        )

        for product_image in product.images.all():
            for field_name in ['thumbnail', 'medium', 'large', 'image']:
                getattr(product_image, field_name).delete(save=False)

        product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductImageUploadView(APIView):
    permission_classes = [IsVendorAdmin]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @extend_schema(
        request=ProductImageSerializer,
        responses={status.HTTP_201_CREATED: ProductImageSerializer},
        tags=['Catalog'],
    )
    def post(self, request, slug):
        product = get_object_or_404(
            Product.all_objects,
            slug=slug,
            tenant=request.user.tenant,
        )
        serializer = ProductImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sort_order = serializer.validated_data.get('sort_order')
        if sort_order is None:
            max_sort_order = ProductImage.all_objects.filter(
                product=product,
                tenant=request.user.tenant,
            ).aggregate(max_sort_order=Max('sort_order'))['max_sort_order']
            sort_order = 0 if max_sort_order is None else max_sort_order + 1
        elif ProductImage.all_objects.filter(
            product=product,
            tenant=request.user.tenant,
            sort_order=sort_order,
        ).exists():
            raise ValidationError({
                'sort_order': 'This sort order is already used for this product.',
            })

        is_primary = serializer.validated_data.get('is_primary', False)
        if is_primary:
            ProductImage.all_objects.filter(
                product=product,
                tenant=request.user.tenant,
                is_primary=True,
            ).update(is_primary=False)

        product_image = serializer.save(
            product=product,
            tenant=request.user.tenant,
            sort_order=sort_order,
            is_primary=is_primary,
        )

        response_serializer = ProductImageSerializer(
            product_image,
            context={'request': request},
        )
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=ProductImageBulkUpdateSerializer,
        responses=ProductImageSerializer(many=True),
        tags=['Catalog'],
    )
    def patch(self, request, slug):
        product = get_object_or_404(
            Product.all_objects,
            slug=slug,
            tenant=request.user.tenant,
        )
        serializer = ProductImageBulkUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        image_updates = serializer.validated_data['images']
        image_ids = [image_update['id'] for image_update in image_updates]
        sort_orders = [
            image_update['sort_order'] for image_update in image_updates
        ]

        if len(image_ids) != len(set(image_ids)):
            raise ValidationError({
                'images': 'Each image can only be included once.',
            })
        if len(sort_orders) != len(set(sort_orders)):
            raise ValidationError({
                'sort_order': 'Each sort order can only be used once.',
            })

        product_images = {
            product_image.id: product_image
            for product_image in ProductImage.all_objects.filter(
                product=product,
                tenant=request.user.tenant,
                id__in=image_ids,
            )
        }
        if len(product_images) != len(image_ids):
            raise ValidationError({
                'images': 'One or more images do not belong to this product.',
            })

        sort_order_conflict = ProductImage.all_objects.filter(
            product=product,
            tenant=request.user.tenant,
            sort_order__in=sort_orders,
        ).exclude(id__in=image_ids).exists()
        if sort_order_conflict:
            raise ValidationError({
                'sort_order': 'One or more sort orders are already in use.',
            })

        primary_updates = [
            image_update for image_update in image_updates
            if image_update.get('is_primary') is True
        ]
        if len(primary_updates) > 1:
            raise ValidationError({
                'is_primary': 'Only one image can be primary.',
            })

        existing_max_sort_order = ProductImage.all_objects.filter(
            product=product,
            tenant=request.user.tenant,
        ).aggregate(max_sort_order=Max('sort_order'))['max_sort_order'] or 0
        temporary_sort_order = max(existing_max_sort_order, max(sort_orders))

        with transaction.atomic():
            for offset, image_update in enumerate(image_updates, start=1):
                product_image = product_images[image_update['id']]
                product_image.sort_order = temporary_sort_order + offset
                product_image.save(update_fields=['sort_order'])

            if primary_updates:
                ProductImage.all_objects.filter(
                    product=product,
                    tenant=request.user.tenant,
                    is_primary=True,
                ).update(is_primary=False)

            for image_update in image_updates:
                product_image = product_images[image_update['id']]
                update_fields = ['sort_order']
                product_image.sort_order = image_update['sort_order']

                if 'alt_text' in image_update:
                    product_image.alt_text = image_update['alt_text']
                    update_fields.append('alt_text')
                if 'is_primary' in image_update:
                    product_image.is_primary = image_update['is_primary']
                    update_fields.append('is_primary')

                product_image.save(update_fields=update_fields)

        updated_images = ProductImage.all_objects.filter(
            product=product,
            tenant=request.user.tenant,
        ).order_by('sort_order', 'id')
        response_serializer = ProductImageSerializer(
            updated_images,
            many=True,
            context={'request': request},
        )
        return Response(response_serializer.data)


class ProductImageDeleteView(APIView):
    permission_classes = [IsVendorAdmin]

    @extend_schema(
        responses={status.HTTP_204_NO_CONTENT: None},
        tags=['Catalog'],
    )
    def delete(self, request, slug, image_id):
        product = get_object_or_404(
            Product.all_objects,
            slug=slug,
            tenant=request.user.tenant,
        )
        product_image = get_object_or_404(
            ProductImage.all_objects,
            id=image_id,
            product=product,
            tenant=request.user.tenant,
        )

        for field_name in ['thumbnail', 'medium', 'large', 'image']:
            getattr(product_image, field_name).delete(save=False)
        product_image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
