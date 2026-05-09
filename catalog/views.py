from django.db import transaction
from django.db.models import Max, Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from users.permissions import IsVendorAdmin

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


class ProductListView(APIView):
    permission_classes = [AllowAny]
    pagination_class = ProductCursorPagination

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsVendorAdmin()]
        return [permission() for permission in self.permission_classes]

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
        return paginator.get_paginated_response(serializer.data)

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


class ProductDetailView(APIView):
    permission_classes = [AllowAny]

    def get_permissions(self):
        if self.request.method == 'PUT':
            return [IsVendorAdmin()]
        return [permission() for permission in self.permission_classes]

    @extend_schema(
        responses=ProductDetailSerializer,
        tags=['Catalog'],
    )
    def get(self, request, slug):
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
        return Response(serializer.data)

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
