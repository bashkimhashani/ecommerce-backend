from django.db.models import Max
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from users.permissions import IsVendorAdmin

from .models import Category, Product, ProductImage
from .serializers import CategoryTreeSerializer, ProductImageSerializer


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


class ProductImageUploadView(APIView):
    permission_classes = [IsVendorAdmin]
    parser_classes = [MultiPartParser, FormParser]

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
