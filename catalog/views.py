from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsVendorAdmin

from .pagination import ProductCursorPagination
from .serializers import (
    CategoryTreeSerializer,
    ProductCreateSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductImageBulkUpdateSerializer,
    ProductImageSerializer,
)
from .services import (
    CatalogQueryService,
    PRICE_RANGES,
    ProductImageService,
    ProductWriteService,
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
        categories = CatalogQueryService.list_category_tree(request.user)
        serializer = CategoryTreeSerializer(categories, many=True)
        return Response(serializer.data)


class ProductAutocompleteView(APIView):
    permission_classes = [AllowAny]
    max_suggestions = 10

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='q',
                type=str,
                required=False,
                description='Autocomplete prefix for product name suggestions.',
            ),
        ],
        responses=inline_serializer(
            name='ProductAutocompleteResponse',
            fields={
                'suggestions': serializers.ListField(
                    child=serializers.CharField(),
                ),
            },
        ),
        tags=['Catalog'],
    )
    def get(self, request):
        return Response({
            'suggestions': CatalogQueryService.autocomplete_product_names(
                user=request.user,
                query=request.query_params.get('q', ''),
                max_suggestions=self.max_suggestions,
            ),
        })


class ProductListView(VendorWritePermissionMixin, APIView):
    permission_classes = [AllowAny]
    pagination_class = ProductCursorPagination
    cache_timeout = 300
    vendor_write_methods = {'POST'}

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
        response_data = CatalogQueryService.get_cached_product_list(
            request,
            lambda: self.get_product_list_data(request),
            self.cache_timeout,
        )
        return Response(response_data)

    def get_product_list_data(self, request):
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(
            CatalogQueryService.active_products_for_user(request.user),
            request,
            view=self,
        )
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
        product = ProductWriteService.create_product(request.user, serializer)
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
    price_ranges = PRICE_RANGES

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
        products, filtered_products = CatalogQueryService.filtered_search_products(
            request.user,
            request.query_params,
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(
            filtered_products,
            request,
            view=self,
        )
        serializer = ProductListSerializer(
            page,
            many=True,
            context={'request': request},
        )
        response = paginator.get_paginated_response(serializer.data)
        response.data['facets'] = CatalogQueryService.product_search_facets(
            products,
        )
        return response


class ProductDetailView(VendorWritePermissionMixin, APIView):
    permission_classes = [AllowAny]
    cache_timeout = 600
    vendor_write_methods = {'PUT', 'DELETE'}

    @extend_schema(
        responses=ProductDetailSerializer,
        tags=['Catalog'],
    )
    def get(self, request, slug):
        response_data = CatalogQueryService.get_cached_product_detail(
            request,
            slug,
            lambda: self.get_product_detail_data(request, slug),
            self.cache_timeout,
        )
        return Response(response_data)

    def get_product_detail_data(self, request, slug):
        product = CatalogQueryService.active_product_detail_for_user(
            request.user,
            slug,
        )
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
        product = ProductWriteService.get_tenant_product(request.user, slug)
        serializer = ProductCreateSerializer(
            product,
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        product = ProductWriteService.update_product(
            request.user,
            product,
            serializer,
        )
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
        ProductWriteService.delete_product(request.user, slug)
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
        product = ProductImageService.get_product_for_user(request.user, slug)
        serializer = ProductImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product_image = ProductImageService.create_image(
            request.user,
            product,
            serializer,
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
        product = ProductImageService.get_product_for_user(request.user, slug)
        serializer = ProductImageBulkUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated_images = ProductImageService.bulk_update_images(
            request.user,
            product,
            serializer.validated_data['images'],
        )
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
        product = ProductImageService.get_product_for_user(request.user, slug)
        ProductImageService.delete_image(request.user, product, image_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
