from hashlib import md5

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Max, Prefetch
from django.shortcuts import get_object_or_404
from django_redis import get_redis_connection
from rest_framework.serializers import ValidationError

from vendor.models import VendorProfile

from .filters import ProductFilter
from .models import Category, Product, ProductImage
from .signals import autocomplete_suggestion_key_for_tenant

PRICE_RANGES = [
    {
        "key": "under_500",
        "label": "Under $500",
        "min": None,
        "max": 500,
        "filters": {"base_price__lt": 500},
    },
    {
        "key": "500_999",
        "label": "$500 - $999",
        "min": 500,
        "max": 999,
        "filters": {
            "base_price__gte": 500,
            "base_price__lt": 1000,
        },
    },
    {
        "key": "1000_1999",
        "label": "$1,000 - $1,999",
        "min": 1000,
        "max": 1999,
        "filters": {
            "base_price__gte": 1000,
            "base_price__lt": 2000,
        },
    },
    {
        "key": "2000_plus",
        "label": "$2,000+",
        "min": 2000,
        "max": None,
        "filters": {"base_price__gte": 2000},
    },
]


class CatalogQueryService:
    @staticmethod
    def list_category_tree(user):
        categories = Category.all_objects.filter(
            parent__isnull=True,
            is_active=True,
        )

        if user.is_authenticated and user.tenant_id:
            categories = categories.filter(tenant=user.tenant)

        return categories.order_by("tree_id", "lft")

    @staticmethod
    def autocomplete_product_names(user, query, max_suggestions=10):
        query = query.strip().lower()
        if not query:
            return []

        tenant_id = getattr(user, "tenant_id", None)
        key = autocomplete_suggestion_key_for_tenant(tenant_id)
        connection = get_redis_connection("default")
        suggestions = []

        for raw_suggestion in connection.zrange(key, 0, -1):
            if isinstance(raw_suggestion, bytes):
                suggestion = raw_suggestion.decode("utf-8")
            else:
                suggestion = raw_suggestion
            if suggestion.lower().startswith(query):
                suggestions.append(suggestion)
            if len(suggestions) >= max_suggestions:
                break

        return suggestions

    @staticmethod
    def product_list_cache_key(request):
        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        tenant_scope = f"tenant:{tenant_id}" if tenant_id else "tenant:public"
        query_hash = md5(
            request.META.get("QUERY_STRING", "").encode("utf-8"),
        ).hexdigest()
        return f"catalog:product-list:{tenant_scope}:{query_hash}"

    @classmethod
    def get_cached_product_list(cls, request, callback, timeout):
        return cache.get_or_set(
            cls.product_list_cache_key(request),
            callback,
            timeout,
        )

    @staticmethod
    def product_detail_cache_key(request, slug):
        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        tenant_scope = f"tenant:{tenant_id}" if tenant_id else "tenant:public"
        return f"catalog:product-detail:{tenant_scope}:{slug}"

    @classmethod
    def get_cached_product_detail(cls, request, slug, callback, timeout):
        return cache.get_or_set(
            cls.product_detail_cache_key(request, slug),
            callback,
            timeout,
        )

    @staticmethod
    def product_images_for_list():
        return ProductImage.all_objects.only(
            "id",
            "product_id",
            "thumbnail",
            "is_primary",
            "sort_order",
        ).order_by("-is_primary", "sort_order", "id")

    @classmethod
    def active_products_for_user(cls, user):
        products = (
            Product.all_objects.filter(
                status=Product.Status.ACTIVE,
            )
            .select_related(
                "brand",
                "category",
                "vendor",
            )
            .prefetch_related(
                Prefetch("images", queryset=cls.product_images_for_list()),
            )
        )

        if user.is_authenticated and user.tenant_id:
            products = products.filter(tenant_id=user.tenant_id)

        return products

    @classmethod
    def active_product_detail_for_user(cls, user, slug):
        products = (
            Product.all_objects.filter(
                status=Product.Status.ACTIVE,
            )
            .select_related(
                "brand",
                "category",
                "vendor",
            )
            .prefetch_related(
                "variants",
                "images",
            )
        )

        if user.is_authenticated and user.tenant_id:
            products = products.filter(tenant_id=user.tenant_id)

        return get_object_or_404(products, slug=slug)

    @classmethod
    def filtered_search_products(cls, user, query_params):
        products = cls.active_products_for_user(user)
        query = query_params.get("q", "").strip()
        if query:
            search_vector = SearchVector("name", weight="A") + SearchVector(
                "description", weight="B"
            )
            search_query = SearchQuery(query)
            products = (
                products.annotate(
                    search=search_vector,
                    search_rank=SearchRank(search_vector, search_query),
                )
                .filter(
                    search=search_query,
                )
                .order_by(
                    "-search_rank",
                    "id",
                )
            )

        product_filter = ProductFilter(
            data=query_params,
            queryset=products,
        )
        if not product_filter.is_valid():
            raise ValidationError(product_filter.errors)

        return products, product_filter.qs

    @staticmethod
    def product_search_facets(products):
        brands = [
            {
                "name": brand["brand__name"],
                "slug": brand["brand__slug"],
                "count": brand["count"],
            }
            for brand in products.order_by()
            .values(
                "brand__name",
                "brand__slug",
            )
            .annotate(
                count=Count("id"),
            )
            .order_by(
                "brand__name",
            )
        ]
        price_ranges = [
            {
                "key": price_range["key"],
                "label": price_range["label"],
                "min": price_range["min"],
                "max": price_range["max"],
                "count": products.filter(**price_range["filters"]).count(),
            }
            for price_range in PRICE_RANGES
        ]

        return {
            "brands": brands,
            "price_ranges": price_ranges,
        }


class ProductWriteService:
    @staticmethod
    def get_request_vendor(user):
        return VendorProfile.objects.filter(
            user=user,
            tenant=user.tenant,
            is_active=True,
        ).first()

    @classmethod
    def create_product(cls, user, serializer):
        return serializer.save(
            tenant=user.tenant,
            vendor=cls.get_request_vendor(user),
        )

    @staticmethod
    def get_tenant_product(user, slug):
        return get_object_or_404(
            Product.all_objects,
            slug=slug,
            tenant_id=user.tenant_id,
        )

    @staticmethod
    def update_product(user, product, serializer):
        return serializer.save(tenant=user.tenant)

    @staticmethod
    def delete_product(user, slug):
        product = get_object_or_404(
            Product.all_objects.prefetch_related("images"),
            slug=slug,
            tenant_id=user.tenant_id,
        )

        for product_image in product.images.all():
            ProductImageService.delete_image_files(product_image)

        product.delete()


class ProductImageService:
    @staticmethod
    def get_product_for_user(user, slug):
        return get_object_or_404(
            Product.all_objects,
            slug=slug,
            tenant=user.tenant,
        )

    @staticmethod
    def delete_image_files(product_image):
        for field_name in ["thumbnail", "medium", "large", "image"]:
            getattr(product_image, field_name).delete(save=False)

    @staticmethod
    def resolve_sort_order(product, tenant, requested_sort_order):
        if requested_sort_order is None:
            max_sort_order = ProductImage.all_objects.filter(
                product=product,
                tenant=tenant,
            ).aggregate(max_sort_order=Max("sort_order"))["max_sort_order"]
            return 0 if max_sort_order is None else max_sort_order + 1

        sort_order_exists = ProductImage.all_objects.filter(
            product=product,
            tenant=tenant,
            sort_order=requested_sort_order,
        ).exists()
        if sort_order_exists:
            raise ValidationError(
                {
                    "sort_order": "This sort order is already used for this product.",
                }
            )

        return requested_sort_order

    @classmethod
    def create_image(cls, user, product, serializer):
        sort_order = cls.resolve_sort_order(
            product,
            user.tenant,
            serializer.validated_data.get("sort_order"),
        )
        is_primary = serializer.validated_data.get("is_primary", False)
        if is_primary:
            ProductImage.all_objects.filter(
                product=product,
                tenant=user.tenant,
                is_primary=True,
            ).update(is_primary=False)

        return serializer.save(
            product=product,
            tenant=user.tenant,
            sort_order=sort_order,
            is_primary=is_primary,
        )

    @staticmethod
    def validate_bulk_updates(product, tenant, image_updates):
        image_ids = [image_update["id"] for image_update in image_updates]
        sort_orders = [image_update["sort_order"] for image_update in image_updates]

        if len(image_ids) != len(set(image_ids)):
            raise ValidationError(
                {
                    "images": "Each image can only be included once.",
                }
            )
        if len(sort_orders) != len(set(sort_orders)):
            raise ValidationError(
                {
                    "sort_order": "Each sort order can only be used once.",
                }
            )

        product_images = {
            product_image.id: product_image
            for product_image in ProductImage.all_objects.filter(
                product=product,
                tenant=tenant,
                id__in=image_ids,
            )
        }
        if len(product_images) != len(image_ids):
            raise ValidationError(
                {
                    "images": "One or more images do not belong to this product.",
                }
            )

        sort_order_conflict = (
            ProductImage.all_objects.filter(
                product=product,
                tenant=tenant,
                sort_order__in=sort_orders,
            )
            .exclude(id__in=image_ids)
            .exists()
        )
        if sort_order_conflict:
            raise ValidationError(
                {
                    "sort_order": "One or more sort orders are already in use.",
                }
            )

        primary_updates = [
            image_update
            for image_update in image_updates
            if image_update.get("is_primary") is True
        ]
        if len(primary_updates) > 1:
            raise ValidationError(
                {
                    "is_primary": "Only one image can be primary.",
                }
            )

        return product_images, primary_updates, sort_orders

    @classmethod
    def bulk_update_images(cls, user, product, image_updates):
        product_images, primary_updates, sort_orders = cls.validate_bulk_updates(
            product,
            user.tenant,
            image_updates,
        )

        existing_max_sort_order = (
            ProductImage.all_objects.filter(
                product=product,
                tenant=user.tenant,
            ).aggregate(max_sort_order=Max("sort_order"))["max_sort_order"]
            or 0
        )
        temporary_sort_order = max(existing_max_sort_order, max(sort_orders))

        with transaction.atomic():
            for offset, image_update in enumerate(image_updates, start=1):
                product_image = product_images[image_update["id"]]
                product_image.sort_order = temporary_sort_order + offset
                product_image.save(update_fields=["sort_order"])

            if primary_updates:
                ProductImage.all_objects.filter(
                    product=product,
                    tenant=user.tenant,
                    is_primary=True,
                ).update(is_primary=False)

            for image_update in image_updates:
                product_image = product_images[image_update["id"]]
                update_fields = ["sort_order"]
                product_image.sort_order = image_update["sort_order"]

                if "alt_text" in image_update:
                    product_image.alt_text = image_update["alt_text"]
                    update_fields.append("alt_text")
                if "is_primary" in image_update:
                    product_image.is_primary = image_update["is_primary"]
                    update_fields.append("is_primary")

                product_image.save(update_fields=update_fields)

        return ProductImage.all_objects.filter(
            product=product,
            tenant=user.tenant,
        ).order_by("sort_order", "id")

    @classmethod
    def delete_image(cls, user, product, image_id):
        product_image = get_object_or_404(
            ProductImage.all_objects,
            id=image_id,
            product=product,
            tenant=user.tenant,
        )
        cls.delete_image_files(product_image)
        product_image.delete()
