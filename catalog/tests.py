import shutil
import tempfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from tenants.models import Tenant

from .models import Brand, Category, Product, ProductImage, ProductVariant
from .serializers import ProductDetailSerializer, ProductListSerializer


User = get_user_model()


class ProductListSerializerTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store',
            domain='acme.example.com',
            plan='basic',
        )
        self.brand = Brand.all_objects.create(
            tenant=self.tenant,
            name='Apple',
            slug='apple',
        )
        self.category = Category.all_objects.create(
            tenant=self.tenant,
            name='Laptops',
            slug='laptops',
        )
        self.product = Product.all_objects.create(
            tenant=self.tenant,
            name='MacBook Air',
            slug='macbook-air',
            sku='MBA-001',
            brand=self.brand,
            category=self.category,
            status='active',
            base_price='999.00',
            tech_specs={'cpu': 'M3'},
        )

    def test_product_list_serializer_returns_lightweight_fields(self):
        serializer = ProductListSerializer(self.product)

        self.assertEqual(
            set(serializer.data.keys()),
            {
                'id',
                'name',
                'slug',
                'price',
                'thumbnail',
                'avg_rating',
            },
        )
        self.assertEqual(serializer.data['name'], 'MacBook Air')
        self.assertEqual(serializer.data['slug'], 'macbook-air')
        self.assertEqual(serializer.data['price'], '999.00')
        self.assertIsNone(serializer.data['thumbnail'])
        self.assertIsNone(serializer.data['avg_rating'])

    def test_product_list_serializer_uses_primary_thumbnail(self):
        ProductImage.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            image='products/images/secondary.jpg',
            thumbnail='products/images/generated/secondary_thumbnail.jpg',
            sort_order=0,
            is_primary=False,
        )
        ProductImage.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            image='products/images/primary.jpg',
            thumbnail='products/images/generated/primary_thumbnail.jpg',
            sort_order=1,
            is_primary=True,
        )

        product = Product.all_objects.prefetch_related('images').get(
            id=self.product.id,
        )
        serializer = ProductListSerializer(product)

        self.assertEqual(
            serializer.data['thumbnail'],
            '/media/products/images/generated/primary_thumbnail.jpg',
        )

    def test_product_list_serializer_returns_annotated_average_rating(self):
        self.product.avg_rating = 4.5

        serializer = ProductListSerializer(self.product)

        self.assertEqual(serializer.data['avg_rating'], 4.5)


class ProductDetailSerializerTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store',
            domain='acme.example.com',
            plan='basic',
        )
        self.brand = Brand.all_objects.create(
            tenant=self.tenant,
            name='Apple',
            slug='apple',
            country_of_origin='United States',
        )
        self.category = Category.all_objects.create(
            tenant=self.tenant,
            name='Laptops',
            slug='laptops',
            icon_url='https://example.com/icons/laptops.svg',
        )
        self.product = Product.all_objects.create(
            tenant=self.tenant,
            name='MacBook Air',
            slug='macbook-air',
            sku='MBA-001',
            brand=self.brand,
            category=self.category,
            status='active',
            base_price='999.00',
            tech_specs={
                'cpu': 'M3',
                'ram': '8GB',
                'storage': '256GB SSD',
            },
        )

    def test_product_detail_serializer_returns_nested_product_fields(self):
        ProductVariant.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            color='Midnight',
            storage='256GB',
            ram='8GB',
            variant_price='999.00',
            stock_quantity=12,
        )
        ProductImage.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            image='products/images/macbook.jpg',
            thumbnail='products/images/generated/macbook_thumbnail.jpg',
            medium='products/images/generated/macbook_medium.jpg',
            large='products/images/generated/macbook_large.jpg',
            alt_text='MacBook Air front view',
            sort_order=0,
            is_primary=True,
        )
        product = Product.all_objects.select_related(
            'brand',
            'category',
        ).prefetch_related(
            'variants',
            'images',
        ).get(id=self.product.id)
        product.avg_rating = 4.75

        serializer = ProductDetailSerializer(product)

        self.assertEqual(serializer.data['name'], 'MacBook Air')
        self.assertEqual(serializer.data['sku'], 'MBA-001')
        self.assertEqual(serializer.data['price'], '999.00')
        self.assertEqual(serializer.data['brand']['slug'], 'apple')
        self.assertEqual(serializer.data['category']['slug'], 'laptops')
        self.assertEqual(serializer.data['specs']['cpu'], 'M3')
        self.assertEqual(serializer.data['avg_rating'], 4.75)
        self.assertEqual(len(serializer.data['variants']), 1)
        self.assertEqual(
            serializer.data['variants'][0]['color'],
            'Midnight',
        )
        self.assertEqual(
            serializer.data['variants'][0]['stock_quantity'],
            12,
        )
        self.assertEqual(len(serializer.data['images']), 1)
        self.assertEqual(
            serializer.data['images'][0]['alt_text'],
            'MacBook Air front view',
        )
        self.assertTrue(serializer.data['images'][0]['is_primary'])


class FakeRedisConnection:
    def __init__(self):
        self.patterns = []
        self.deleted_keys = []

    def scan_iter(self, match):
        self.patterns.append(match)
        return [f'cache:{match}'.encode('utf-8')]

    def delete(self, *keys):
        self.deleted_keys.extend(keys)
        return len(keys)


class ProductCacheInvalidationSignalTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store-cache-signals',
            domain='cache-signals.acme.example.com',
            plan='basic',
        )
        self.brand = Brand.all_objects.create(
            tenant=self.tenant,
            name='Apple',
            slug='apple-cache-signals',
        )
        self.category = Category.all_objects.create(
            tenant=self.tenant,
            name='Laptops',
            slug='laptops-cache-signals',
        )

    def create_product(self, **overrides):
        defaults = {
            'tenant': self.tenant,
            'name': 'MacBook Air',
            'slug': 'macbook-air-cache-signals',
            'sku': 'MBA-CACHE-SIGNALS-001',
            'brand': self.brand,
            'category': self.category,
            'status': Product.Status.ACTIVE,
            'base_price': '999.00',
            'tech_specs': {'cpu': 'M3'},
        }
        defaults.update(overrides)
        return Product.all_objects.create(**defaults)

    def expected_patterns(self, product):
        tenant_scope = f'tenant:{self.tenant.id}'
        return [
            f'*catalog:product-list:{tenant_scope}:*',
            '*catalog:product-list:tenant:public:*',
            f'*catalog:product-detail:{tenant_scope}:{product.slug}',
            f'*catalog:product-detail:tenant:public:{product.slug}',
        ]

    def test_product_post_save_invalidates_list_and_detail_cache_patterns(self):
        connection = FakeRedisConnection()

        with patch(
            'catalog.signals.get_redis_connection',
            return_value=connection,
        ):
            product = self.create_product()

        self.assertEqual(connection.patterns, self.expected_patterns(product))
        self.assertEqual(len(connection.deleted_keys), 4)

    def test_product_post_delete_invalidates_list_and_detail_cache_patterns(self):
        product = self.create_product()
        connection = FakeRedisConnection()

        with patch(
            'catalog.signals.get_redis_connection',
            return_value=connection,
        ):
            product.delete()

        self.assertEqual(connection.patterns, self.expected_patterns(product))
        self.assertEqual(len(connection.deleted_keys), 4)


class CategoryTreeEndpointTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store',
            domain='acme.example.com',
            plan='basic',
        )
        self.user = User.objects.create_user(
            email='vendor@example.com',
            password='StrongPass123',
            first_name='Vendor',
            last_name='Admin',
            role='vendor_admin',
            tenant=self.tenant,
        )
        self.url = reverse('category-tree')

    def test_category_tree_returns_nested_active_categories(self):
        laptops = Category.all_objects.create(
            tenant=self.tenant,
            name='Laptops',
            slug='laptops',
            icon_url='https://example.com/icons/laptops.svg',
        )
        ultrabooks = Category.all_objects.create(
            tenant=self.tenant,
            parent=laptops,
            name='Ultrabooks',
            slug='ultrabooks',
        )
        Category.all_objects.create(
            tenant=self.tenant,
            parent=ultrabooks,
            name='Business Ultrabooks',
            slug='business-ultrabooks',
        )
        Category.all_objects.create(
            tenant=self.tenant,
            parent=laptops,
            name='Inactive Gaming',
            slug='inactive-gaming',
            is_active=False,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['slug'], 'laptops')
        self.assertEqual(response.data[0]['icon_url'], laptops.icon_url)
        self.assertEqual(len(response.data[0]['children']), 1)
        self.assertEqual(response.data[0]['children'][0]['slug'], 'ultrabooks')
        self.assertEqual(
            response.data[0]['children'][0]['children'][0]['slug'],
            'business-ultrabooks',
        )

    def test_category_tree_excludes_other_tenants_for_authenticated_user(self):
        other_tenant = Tenant.objects.create(
            name='Other Store',
            slug='other-store',
            domain='other.example.com',
            plan='basic',
        )
        Category.all_objects.create(
            tenant=self.tenant,
            name='Accessories',
            slug='accessories',
        )
        Category.all_objects.create(
            tenant=other_tenant,
            name='Other Accessories',
            slug='other-accessories',
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [category['slug'] for category in response.data],
            ['accessories'],
        )

    def test_category_tree_excludes_inactive_root_categories(self):
        Category.all_objects.create(
            tenant=self.tenant,
            name='Active Root',
            slug='active-root',
        )
        Category.all_objects.create(
            tenant=self.tenant,
            name='Inactive Root',
            slug='inactive-root',
            is_active=False,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [category['slug'] for category in response.data],
            ['active-root'],
        )

    def test_category_tree_response_contains_expected_fields(self):
        Category.all_objects.create(
            tenant=self.tenant,
            name='Monitors',
            slug='monitors',
            icon_url='https://example.com/icons/monitors.svg',
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data[0].keys()),
            {
                'id',
                'name',
                'slug',
                'icon_url',
                'is_active',
                'children',
            },
        )
        self.assertEqual(response.data[0]['slug'], 'monitors')
        self.assertEqual(response.data[0]['children'], [])

    def test_category_tree_endpoint_allows_anonymous_customers(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)


class ProductListEndpointTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store-products',
            domain='products.acme.example.com',
            plan='basic',
        )
        self.user = User.objects.create_user(
            email='product-vendor@example.com',
            password='StrongPass123',
            first_name='Product',
            last_name='Vendor',
            role='vendor_admin',
            tenant=self.tenant,
        )
        self.brand = Brand.all_objects.create(
            tenant=self.tenant,
            name='Apple',
            slug='apple-products',
        )
        self.category = Category.all_objects.create(
            tenant=self.tenant,
            name='Laptops',
            slug='laptops-products',
        )
        self.url = reverse('product-list')

    def create_product(self, **overrides):
        defaults = {
            'tenant': self.tenant,
            'name': 'MacBook Air',
            'slug': 'macbook-air-list',
            'sku': 'MBA-LIST-001',
            'brand': self.brand,
            'category': self.category,
            'status': Product.Status.ACTIVE,
            'base_price': '999.00',
            'tech_specs': {'cpu': 'M3'},
        }
        defaults.update(overrides)
        return Product.all_objects.create(**defaults)

    def test_product_list_endpoint_returns_active_products(self):
        active_product = self.create_product()
        self.create_product(
            name='Draft MacBook',
            slug='draft-macbook-list',
            sku='DRAFT-LIST-001',
            status=Product.Status.DRAFT,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], active_product.id)
        self.assertEqual(response.data['results'][0]['name'], 'MacBook Air')
        self.assertEqual(response.data['results'][0]['price'], '999.00')

    def test_product_list_endpoint_response_uses_lightweight_shape(self):
        self.create_product()
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data.keys()),
            {
                'next',
                'previous',
                'results',
            },
        )
        self.assertIsNone(response.data['next'])
        self.assertIsNone(response.data['previous'])
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(
            set(response.data['results'][0].keys()),
            {
                'id',
                'name',
                'slug',
                'price',
                'thumbnail',
                'avg_rating',
            },
        )

    def test_product_list_endpoint_scopes_authenticated_user_to_tenant(self):
        own_product = self.create_product()
        other_tenant = Tenant.objects.create(
            name='Other Store',
            slug='other-store-products',
            domain='products.other.example.com',
            plan='basic',
        )
        other_brand = Brand.all_objects.create(
            tenant=other_tenant,
            name='Dell',
            slug='dell-products',
        )
        other_category = Category.all_objects.create(
            tenant=other_tenant,
            name='Laptops',
            slug='other-laptops-products',
        )
        self.create_product(
            tenant=other_tenant,
            name='Dell XPS',
            slug='dell-xps-list',
            sku='DXPS-LIST-001',
            brand=other_brand,
            category=other_category,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [product['id'] for product in response.data['results']],
            [own_product.id],
        )

    def test_product_list_endpoint_returns_thumbnail_url(self):
        product = self.create_product()
        ProductImage.all_objects.create(
            tenant=self.tenant,
            product=product,
            image='products/images/macbook.jpg',
            thumbnail='products/images/generated/macbook_thumbnail.jpg',
            sort_order=0,
            is_primary=True,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['results'][0]['thumbnail'],
            'http://testserver/media/products/images/generated/'
            'macbook_thumbnail.jpg',
        )

    def test_product_list_endpoint_prefetches_images_without_n_plus_one(self):
        for product_number in range(5):
            product = self.create_product(
                name=f'MacBook Air {product_number}',
                slug=f'macbook-air-list-{product_number}',
                sku=f'MBA-LIST-{product_number}',
            )
            ProductImage.all_objects.create(
                tenant=self.tenant,
                product=product,
                image=f'products/images/macbook-{product_number}.jpg',
                thumbnail=(
                    'products/images/generated/'
                    f'macbook-{product_number}_thumbnail.jpg'
                ),
                sort_order=0,
                is_primary=True,
            )
        self.client.force_authenticate(user=self.user)

        with self.assertNumQueries(2):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 5)
        self.assertTrue(
            all(product['thumbnail'] for product in response.data['results'])
        )

    def test_product_list_endpoint_uses_cache_get_or_set_with_300s_ttl(self):
        self.create_product()
        self.client.force_authenticate(user=self.user)

        with patch('catalog.views.cache.get_or_set') as get_or_set:
            get_or_set.side_effect = (
                lambda cache_key, default, timeout: default()
            )

            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        get_or_set.assert_called_once()
        cache_key, default, timeout = get_or_set.call_args.args
        self.assertTrue(
            cache_key.startswith(
                f'catalog:product-list:tenant:{self.tenant.id}:',
            )
        )
        self.assertEqual(timeout, 300)
        self.assertTrue(callable(default))

    def test_product_list_endpoint_uses_cursor_pagination_page_size_24(self):
        paged_products = []
        for product_number in range(25):
            paged_products.append(self.create_product(
                name=f'Paged Product {product_number:02}',
                slug=f'paged-product-{product_number:02}',
                sku=f'PAGED-{product_number:02}',
            ))
        self.client.force_authenticate(user=self.user)

        first_response = self.client.get(self.url)

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(first_response.data['results']), 24)
        self.assertEqual(
            [product['id'] for product in first_response.data['results']],
            [product.id for product in paged_products[:24]],
        )
        self.assertIsNotNone(first_response.data['next'])
        self.assertIsNone(first_response.data['previous'])

        next_url = first_response.data['next'].replace(
            'http://testserver',
            '',
        )
        second_response = self.client.get(next_url)

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(second_response.data['results']), 1)
        self.assertEqual(
            [product['id'] for product in second_response.data['results']],
            [paged_products[24].id],
        )
        self.assertIsNone(second_response.data['next'])
        self.assertIsNotNone(second_response.data['previous'])


class ProductCreateEndpointTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store-create',
            domain='create.acme.example.com',
            plan='basic',
        )
        self.vendor = User.objects.create_user(
            email='create-vendor@example.com',
            password='StrongPass123',
            first_name='Create',
            last_name='Vendor',
            role='vendor_admin',
            tenant=self.tenant,
        )
        self.customer = User.objects.create_user(
            email='create-customer@example.com',
            password='StrongPass123',
            first_name='Create',
            last_name='Customer',
            role='customer',
            tenant=self.tenant,
        )
        self.brand = Brand.all_objects.create(
            tenant=self.tenant,
            name='Apple',
            slug='apple-create',
        )
        self.category = Category.all_objects.create(
            tenant=self.tenant,
            name='Laptops',
            slug='laptops-create',
        )
        self.url = reverse('product-list')

    def product_payload(self, **overrides):
        payload = {
            'name': 'MacBook Air 15',
            'slug': 'macbook-air-15-create',
            'sku': 'MBA15-CREATE-001',
            'brand': self.brand.id,
            'category': self.category.id,
            'status': Product.Status.ACTIVE,
            'base_price': '1299.00',
            'tech_specs': {
                'cpu': 'M3',
                'ram': '16GB',
                'storage': '512GB SSD',
            },
        }
        payload.update(overrides)
        return payload

    def test_vendor_can_create_product(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.url,
            self.product_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        product = Product.all_objects.get(slug='macbook-air-15-create')
        self.assertEqual(product.tenant, self.tenant)
        self.assertEqual(product.brand, self.brand)
        self.assertEqual(product.category, self.category)
        self.assertEqual(product.sku, 'MBA15-CREATE-001')
        self.assertEqual(product.tech_specs['ram'], '16GB')
        self.assertEqual(response.data['slug'], product.slug)
        self.assertEqual(response.data['brand']['id'], self.brand.id)
        self.assertEqual(response.data['category']['id'], self.category.id)
        self.assertEqual(response.data['specs']['storage'], '512GB SSD')

    def test_non_vendor_cannot_create_product(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            self.url,
            self.product_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            Product.all_objects.filter(slug='macbook-air-15-create').exists()
        )

    def test_anonymous_user_cannot_create_product(self):
        response = self.client.post(
            self.url,
            self.product_payload(),
            format='json',
        )

        self.assertIn(
            response.status_code,
            [
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ],
        )
        self.assertFalse(
            Product.all_objects.filter(slug='macbook-air-15-create').exists()
        )

    def test_create_rejects_brand_from_other_tenant(self):
        other_tenant = Tenant.objects.create(
            name='Other Store',
            slug='other-store-create',
            domain='create.other.example.com',
            plan='basic',
        )
        other_brand = Brand.all_objects.create(
            tenant=other_tenant,
            name='Dell',
            slug='dell-create',
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.url,
            self.product_payload(brand=other_brand.id),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('brand', response.data)

    def test_create_rejects_category_from_other_tenant(self):
        other_tenant = Tenant.objects.create(
            name='Other Category Store',
            slug='other-category-store-create',
            domain='create-category.other.example.com',
            plan='basic',
        )
        other_category = Category.all_objects.create(
            tenant=other_tenant,
            name='Other Laptops',
            slug='other-laptops-create',
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.url,
            self.product_payload(category=other_category.id),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('category', response.data)

    def test_create_allows_same_slug_and_sku_in_different_tenant(self):
        other_tenant = Tenant.objects.create(
            name='Other Duplicate Store',
            slug='other-duplicate-store-create',
            domain='create-duplicate.other.example.com',
            plan='basic',
        )
        other_brand = Brand.all_objects.create(
            tenant=other_tenant,
            name='Dell',
            slug='dell-duplicate-create',
        )
        other_category = Category.all_objects.create(
            tenant=other_tenant,
            name='Laptops',
            slug='other-laptops-duplicate-create',
        )
        Product.all_objects.create(
            tenant=other_tenant,
            name='Other MacBook Air 15',
            slug='macbook-air-15-create',
            sku='MBA15-CREATE-001',
            brand=other_brand,
            category=other_category,
            status=Product.Status.ACTIVE,
            base_price='1299.00',
            tech_specs={'cpu': 'M3'},
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.url,
            self.product_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        product = Product.all_objects.get(
            tenant=self.tenant,
            slug='macbook-air-15-create',
        )
        self.assertEqual(product.sku, 'MBA15-CREATE-001')
        self.assertEqual(product.tenant, self.tenant)

    def test_create_rejects_duplicate_slug_and_sku_for_tenant(self):
        Product.all_objects.create(
            tenant=self.tenant,
            name='Existing Product',
            slug='macbook-air-15-create',
            sku='MBA15-CREATE-001',
            brand=self.brand,
            category=self.category,
            status=Product.Status.ACTIVE,
            base_price='1299.00',
            tech_specs={'cpu': 'M3'},
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.url,
            self.product_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('slug', response.data)
        self.assertIn('sku', response.data)


class ProductUpdateEndpointTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store-update',
            domain='update.acme.example.com',
            plan='basic',
        )
        self.vendor = User.objects.create_user(
            email='update-vendor@example.com',
            password='StrongPass123',
            first_name='Update',
            last_name='Vendor',
            role='vendor_admin',
            tenant=self.tenant,
        )
        self.customer = User.objects.create_user(
            email='update-customer@example.com',
            password='StrongPass123',
            first_name='Update',
            last_name='Customer',
            role='customer',
            tenant=self.tenant,
        )
        self.brand = Brand.all_objects.create(
            tenant=self.tenant,
            name='Apple',
            slug='apple-update',
        )
        self.category = Category.all_objects.create(
            tenant=self.tenant,
            name='Laptops',
            slug='laptops-update',
        )
        self.product = Product.all_objects.create(
            tenant=self.tenant,
            name='MacBook Air 13',
            slug='macbook-air-13-update',
            sku='MBA13-UPDATE-001',
            brand=self.brand,
            category=self.category,
            status=Product.Status.DRAFT,
            base_price='999.00',
            tech_specs={'cpu': 'M2'},
        )
        self.url = reverse(
            'product-detail',
            kwargs={'slug': self.product.slug},
        )

    def product_payload(self, **overrides):
        payload = {
            'name': 'MacBook Air 13 M3',
            'slug': 'macbook-air-13-m3-update',
            'sku': 'MBA13-M3-UPDATE-001',
            'brand': self.brand.id,
            'category': self.category.id,
            'status': Product.Status.ACTIVE,
            'base_price': '1099.00',
            'tech_specs': {
                'cpu': 'M3',
                'ram': '16GB',
                'storage': '512GB SSD',
            },
        }
        payload.update(overrides)
        return payload

    def test_vendor_can_update_product(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.put(
            self.url,
            self.product_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, 'MacBook Air 13 M3')
        self.assertEqual(self.product.slug, 'macbook-air-13-m3-update')
        self.assertEqual(self.product.sku, 'MBA13-M3-UPDATE-001')
        self.assertEqual(self.product.status, Product.Status.ACTIVE)
        self.assertEqual(str(self.product.base_price), '1099.00')
        self.assertEqual(self.product.tech_specs['storage'], '512GB SSD')
        self.assertEqual(self.product.tenant, self.tenant)
        self.assertEqual(response.data['slug'], self.product.slug)
        self.assertEqual(response.data['specs']['cpu'], 'M3')

    def test_non_vendor_cannot_update_product(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.put(
            self.url,
            self.product_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.product.refresh_from_db()
        self.assertEqual(self.product.slug, 'macbook-air-13-update')

    def test_vendor_cannot_update_other_tenant_product(self):
        other_tenant = Tenant.objects.create(
            name='Other Store',
            slug='other-store-update',
            domain='update.other.example.com',
            plan='basic',
        )
        other_brand = Brand.all_objects.create(
            tenant=other_tenant,
            name='Dell',
            slug='dell-update',
        )
        other_category = Category.all_objects.create(
            tenant=other_tenant,
            name='Laptops',
            slug='other-laptops-update',
        )
        other_product = Product.all_objects.create(
            tenant=other_tenant,
            name='Dell XPS',
            slug='dell-xps-update',
            sku='DXPS-UPDATE-001',
            brand=other_brand,
            category=other_category,
            status=Product.Status.ACTIVE,
            base_price='1299.00',
            tech_specs={'cpu': 'Intel Core Ultra'},
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.put(
            reverse('product-detail', kwargs={'slug': other_product.slug}),
            self.product_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_rejects_duplicate_slug_and_sku_for_tenant(self):
        Product.all_objects.create(
            tenant=self.tenant,
            name='Existing Product',
            slug='existing-product-update',
            sku='EXISTING-UPDATE-001',
            brand=self.brand,
            category=self.category,
            status=Product.Status.ACTIVE,
            base_price='1499.00',
            tech_specs={'cpu': 'M3 Pro'},
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.put(
            self.url,
            self.product_payload(
                slug='existing-product-update',
                sku='EXISTING-UPDATE-001',
            ),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('slug', response.data)
        self.assertIn('sku', response.data)


class ProductDeleteEndpointTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store-delete',
            domain='delete.acme.example.com',
            plan='basic',
        )
        self.vendor = User.objects.create_user(
            email='delete-vendor@example.com',
            password='StrongPass123',
            first_name='Delete',
            last_name='Vendor',
            role='vendor_admin',
            tenant=self.tenant,
        )
        self.customer = User.objects.create_user(
            email='delete-customer@example.com',
            password='StrongPass123',
            first_name='Delete',
            last_name='Customer',
            role='customer',
            tenant=self.tenant,
        )
        self.brand = Brand.all_objects.create(
            tenant=self.tenant,
            name='Apple',
            slug='apple-delete',
        )
        self.category = Category.all_objects.create(
            tenant=self.tenant,
            name='Laptops',
            slug='laptops-delete',
        )
        self.product = Product.all_objects.create(
            tenant=self.tenant,
            name='MacBook Air Delete',
            slug='macbook-air-delete',
            sku='MBA-DELETE-001',
            brand=self.brand,
            category=self.category,
            status=Product.Status.ACTIVE,
            base_price='999.00',
            tech_specs={'cpu': 'M2'},
        )
        self.url = reverse(
            'product-detail',
            kwargs={'slug': self.product.slug},
        )

    def test_vendor_can_delete_product(self):
        product_image = ProductImage.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            image='products/images/delete.jpg',
            thumbnail='products/images/generated/delete_thumbnail.jpg',
            sort_order=0,
            is_primary=True,
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            Product.all_objects.filter(id=self.product.id).exists()
        )
        self.assertFalse(
            ProductImage.all_objects.filter(id=product_image.id).exists()
        )

    def test_non_vendor_cannot_delete_product(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(
            Product.all_objects.filter(id=self.product.id).exists()
        )

    def test_vendor_cannot_delete_other_tenant_product(self):
        other_tenant = Tenant.objects.create(
            name='Other Store',
            slug='other-store-delete',
            domain='delete.other.example.com',
            plan='basic',
        )
        other_brand = Brand.all_objects.create(
            tenant=other_tenant,
            name='Dell',
            slug='dell-delete',
        )
        other_category = Category.all_objects.create(
            tenant=other_tenant,
            name='Laptops',
            slug='other-laptops-delete',
        )
        other_product = Product.all_objects.create(
            tenant=other_tenant,
            name='Dell XPS Delete',
            slug='dell-xps-delete',
            sku='DXPS-DELETE-001',
            brand=other_brand,
            category=other_category,
            status=Product.Status.ACTIVE,
            base_price='1299.00',
            tech_specs={'cpu': 'Intel Core Ultra'},
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.delete(
            reverse('product-detail', kwargs={'slug': other_product.slug}),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(
            Product.all_objects.filter(id=other_product.id).exists()
        )


class ProductDetailEndpointTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store-detail',
            domain='detail.acme.example.com',
            plan='basic',
        )
        self.user = User.objects.create_user(
            email='detail-vendor@example.com',
            password='StrongPass123',
            first_name='Detail',
            last_name='Vendor',
            role='vendor_admin',
            tenant=self.tenant,
        )
        self.brand = Brand.all_objects.create(
            tenant=self.tenant,
            name='Apple',
            slug='apple-detail',
            country_of_origin='United States',
        )
        self.category = Category.all_objects.create(
            tenant=self.tenant,
            name='Laptops',
            slug='laptops-detail',
            icon_url='https://example.com/icons/laptops.svg',
        )
        self.product = Product.all_objects.create(
            tenant=self.tenant,
            name='MacBook Pro 14',
            slug='macbook-pro-14-detail',
            sku='MBP14-DETAIL-001',
            brand=self.brand,
            category=self.category,
            status=Product.Status.ACTIVE,
            base_price='1999.00',
            tech_specs={
                'cpu': 'M3 Pro',
                'ram': '18GB',
                'storage': '512GB SSD',
            },
        )
        self.url = reverse(
            'product-detail',
            kwargs={'slug': self.product.slug},
        )

    def test_product_detail_endpoint_returns_nested_product(self):
        ProductVariant.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            color='Space Black',
            storage='512GB',
            ram='18GB',
            variant_price='1999.00',
            stock_quantity=8,
        )
        ProductImage.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            image='products/images/macbook-pro.jpg',
            thumbnail='products/images/generated/macbook-pro_thumbnail.jpg',
            medium='products/images/generated/macbook-pro_medium.jpg',
            large='products/images/generated/macbook-pro_large.jpg',
            alt_text='MacBook Pro open on desk',
            sort_order=0,
            is_primary=True,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'MacBook Pro 14')
        self.assertEqual(response.data['slug'], self.product.slug)
        self.assertEqual(response.data['sku'], 'MBP14-DETAIL-001')
        self.assertEqual(response.data['price'], '1999.00')
        self.assertEqual(response.data['brand']['slug'], 'apple-detail')
        self.assertEqual(response.data['category']['slug'], 'laptops-detail')
        self.assertEqual(response.data['specs']['cpu'], 'M3 Pro')
        self.assertEqual(len(response.data['variants']), 1)
        self.assertEqual(
            response.data['variants'][0]['stock_quantity'],
            8,
        )
        self.assertEqual(len(response.data['images']), 1)
        self.assertTrue(response.data['images'][0]['is_primary'])
        self.assertEqual(
            response.data['images'][0]['alt_text'],
            'MacBook Pro open on desk',
        )

    def test_product_detail_endpoint_response_has_nested_serializer_fields(self):
        first_variant = ProductVariant.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            color='Space Black',
            storage='512GB',
            ram='18GB',
            variant_price='1999.00',
            stock_quantity=8,
        )
        second_variant = ProductVariant.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            color='Silver',
            storage='1TB',
            ram='36GB',
            variant_price='2499.00',
            stock_quantity=4,
        )
        ProductImage.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            image='products/images/macbook-pro-front.jpg',
            thumbnail='products/images/generated/front_thumbnail.jpg',
            medium='products/images/generated/front_medium.jpg',
            large='products/images/generated/front_large.jpg',
            alt_text='MacBook Pro front',
            sort_order=0,
            is_primary=True,
        )
        ProductImage.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            image='products/images/macbook-pro-side.jpg',
            thumbnail='products/images/generated/side_thumbnail.jpg',
            medium='products/images/generated/side_medium.jpg',
            large='products/images/generated/side_large.jpg',
            alt_text='MacBook Pro side',
            sort_order=1,
            is_primary=False,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data.keys()),
            {
                'id',
                'name',
                'slug',
                'sku',
                'brand',
                'category',
                'status',
                'price',
                'specs',
                'variants',
                'images',
                'avg_rating',
                'created_at',
                'updated_at',
            },
        )
        self.assertEqual(
            set(response.data['brand'].keys()),
            {
                'id',
                'name',
                'slug',
                'logo',
                'country_of_origin',
            },
        )
        self.assertEqual(
            set(response.data['category'].keys()),
            {
                'id',
                'name',
                'slug',
                'icon_url',
            },
        )
        self.assertEqual(
            set(response.data['variants'][0].keys()),
            {
                'id',
                'color',
                'storage',
                'ram',
                'variant_price',
                'stock_quantity',
            },
        )
        self.assertEqual(
            set(response.data['images'][0].keys()),
            {
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
            },
        )
        self.assertEqual(response.data['specs']['storage'], '512GB SSD')
        self.assertEqual(
            [variant['id'] for variant in response.data['variants']],
            [second_variant.id, first_variant.id],
        )
        self.assertEqual(
            [image['sort_order'] for image in response.data['images']],
            [0, 1],
        )
        self.assertEqual(
            response.data['images'][0]['large'],
            'http://testserver/media/products/images/generated/front_large.jpg',
        )

    def test_product_detail_endpoint_prefetches_nested_serializer_fields(self):
        ProductVariant.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            color='Space Black',
            storage='512GB',
            ram='18GB',
            variant_price='1999.00',
            stock_quantity=8,
        )
        ProductImage.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            image='products/images/macbook-pro-front.jpg',
            thumbnail='products/images/generated/front_thumbnail.jpg',
            medium='products/images/generated/front_medium.jpg',
            large='products/images/generated/front_large.jpg',
            sort_order=0,
            is_primary=True,
        )

        with self.assertNumQueries(3):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['variants']), 1)
        self.assertEqual(len(response.data['images']), 1)

    def test_product_detail_endpoint_uses_cache_get_or_set_with_600s_ttl(self):
        with patch('catalog.views.cache.get_or_set') as get_or_set:
            get_or_set.side_effect = (
                lambda cache_key, default, timeout: default()
            )

            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        get_or_set.assert_called_once()
        cache_key, default, timeout = get_or_set.call_args.args
        self.assertEqual(
            cache_key,
            f'catalog:product-detail:tenant:public:{self.product.slug}',
        )
        self.assertEqual(timeout, 600)
        self.assertTrue(callable(default))

    def test_product_detail_endpoint_returns_404_for_inactive_product(self):
        draft_product = Product.all_objects.create(
            tenant=self.tenant,
            name='Draft Product',
            slug='draft-product-detail',
            sku='DRAFT-DETAIL-001',
            brand=self.brand,
            category=self.category,
            status=Product.Status.DRAFT,
            base_price='899.00',
            tech_specs={'cpu': 'M2'},
        )

        response = self.client.get(
            reverse('product-detail', kwargs={'slug': draft_product.slug}),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_product_detail_endpoint_scopes_authenticated_user_to_tenant(self):
        other_tenant = Tenant.objects.create(
            name='Other Store',
            slug='other-store-detail',
            domain='detail.other.example.com',
            plan='basic',
        )
        other_brand = Brand.all_objects.create(
            tenant=other_tenant,
            name='Dell',
            slug='dell-detail',
        )
        other_category = Category.all_objects.create(
            tenant=other_tenant,
            name='Laptops',
            slug='other-laptops-detail',
        )
        other_product = Product.all_objects.create(
            tenant=other_tenant,
            name='Dell XPS Detail',
            slug='dell-xps-detail',
            sku='DXPS-DETAIL-001',
            brand=other_brand,
            category=other_category,
            status=Product.Status.ACTIVE,
            base_price='1299.00',
            tech_specs={'cpu': 'Intel Core Ultra'},
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            reverse('product-detail', kwargs={'slug': other_product.slug}),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ProductImageUploadEndpointTests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(shutil.rmtree, self.media_root)

        self.tenant = Tenant.objects.create(
            name='Acme Store',
            slug='acme-store',
            domain='acme.example.com',
            plan='basic',
        )
        self.vendor = User.objects.create_user(
            email='vendor@example.com',
            password='StrongPass123',
            first_name='Vendor',
            last_name='Admin',
            role='vendor_admin',
            tenant=self.tenant,
        )
        self.customer = User.objects.create_user(
            email='customer@example.com',
            password='StrongPass123',
            first_name='Customer',
            last_name='User',
            role='customer',
            tenant=self.tenant,
        )
        self.brand = Brand.all_objects.create(
            tenant=self.tenant,
            name='Apple',
            slug='apple',
        )
        self.category = Category.all_objects.create(
            tenant=self.tenant,
            name='Laptops',
            slug='laptops',
        )
        self.product = Product.all_objects.create(
            tenant=self.tenant,
            name='MacBook Air',
            slug='macbook-air',
            sku='MBA-001',
            brand=self.brand,
            category=self.category,
            status='active',
            base_price='999.00',
            tech_specs={'cpu': 'M3'},
        )
        self.url = reverse(
            'product-image-upload',
            kwargs={'slug': self.product.slug},
        )

    def image_upload(self, name='product.jpg', size=(1600, 1200)):
        image = Image.new('RGB', size, color='white')
        output = BytesIO()
        image.save(output, format='JPEG')
        output.seek(0)
        return SimpleUploadedFile(
            name,
            output.read(),
            content_type='image/jpeg',
        )

    def test_vendor_can_upload_product_image(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.url,
            {
                'image': self.image_upload(),
                'alt_text': 'MacBook Air front view',
                'is_primary': True,
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        product_image = ProductImage.all_objects.get()
        self.assertEqual(product_image.product, self.product)
        self.assertEqual(product_image.tenant, self.tenant)
        self.assertEqual(product_image.alt_text, 'MacBook Air front view')
        self.assertEqual(product_image.sort_order, 0)
        self.assertTrue(product_image.is_primary)
        self.assertEqual(response.data['id'], product_image.id)

    def test_upload_generates_thumbnail_medium_and_large_images(self):
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.url,
            {'image': self.image_upload()},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        product_image = ProductImage.all_objects.get()
        self.assertTrue(product_image.thumbnail.name)
        self.assertTrue(product_image.medium.name)
        self.assertTrue(product_image.large.name)
        self.assertTrue(product_image.thumbnail.storage.exists(
            product_image.thumbnail.name,
        ))
        self.assertTrue(product_image.medium.storage.exists(
            product_image.medium.name,
        ))
        self.assertTrue(product_image.large.storage.exists(
            product_image.large.name,
        ))

        expected_sizes = [
            (product_image.thumbnail, (150, 150)),
            (product_image.medium, (600, 600)),
            (product_image.large, (1200, 1200)),
        ]
        for image_field, max_size in expected_sizes:
            image_field.open('rb')
            generated_image = Image.open(image_field)
            generated_image.load()
            image_field.close()
            self.assertLessEqual(generated_image.width, max_size[0])
            self.assertLessEqual(generated_image.height, max_size[1])

    def test_upload_assigns_next_sort_order_when_not_provided(self):
        ProductImage.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            image='products/images/existing.gif',
            sort_order=3,
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.url,
            {
                'image': self.image_upload('next.gif'),
                'alt_text': 'Next image',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['sort_order'], 4)

    def test_upload_rejects_duplicate_sort_order_for_product(self):
        ProductImage.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            image='products/images/existing.gif',
            sort_order=1,
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            self.url,
            {
                'image': self.image_upload('duplicate.gif'),
                'sort_order': 1,
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('sort_order', response.data)

    def test_non_vendor_cannot_upload_product_image(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            self.url,
            {'image': self.image_upload()},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ProductImage.all_objects.exists())

    def test_vendor_cannot_upload_image_for_other_tenant_product(self):
        other_tenant = Tenant.objects.create(
            name='Other Store',
            slug='other-store',
            domain='other.example.com',
            plan='basic',
        )
        other_brand = Brand.all_objects.create(
            tenant=other_tenant,
            name='Dell',
            slug='dell',
        )
        other_category = Category.all_objects.create(
            tenant=other_tenant,
            name='Laptops',
            slug='other-laptops',
        )
        other_product = Product.all_objects.create(
            tenant=other_tenant,
            name='Dell XPS',
            slug='dell-xps',
            sku='DXPS-001',
            brand=other_brand,
            category=other_category,
            status='active',
            base_price='1199.00',
            tech_specs={'cpu': 'Intel Core Ultra'},
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.post(
            reverse('product-image-upload', kwargs={'slug': other_product.slug}),
            {'image': self.image_upload()},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(ProductImage.all_objects.exists())

    def create_product_image(self, sort_order, is_primary=False, alt_text=''):
        return ProductImage.all_objects.create(
            tenant=self.tenant,
            product=self.product,
            image=f'products/images/image-{sort_order}.gif',
            alt_text=alt_text,
            sort_order=sort_order,
            is_primary=is_primary,
        )

    def test_vendor_can_reorder_product_images(self):
        first_image = self.create_product_image(0, alt_text='First')
        second_image = self.create_product_image(1, alt_text='Second')
        third_image = self.create_product_image(2, alt_text='Third')
        self.client.force_authenticate(user=self.vendor)

        response = self.client.patch(
            self.url,
            {
                'images': [
                    {'id': third_image.id, 'sort_order': 0},
                    {
                        'id': first_image.id,
                        'sort_order': 1,
                        'alt_text': 'Updated first',
                    },
                    {'id': second_image.id, 'sort_order': 2},
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [image['id'] for image in response.data],
            [third_image.id, first_image.id, second_image.id],
        )
        first_image.refresh_from_db()
        second_image.refresh_from_db()
        third_image.refresh_from_db()
        self.assertEqual(third_image.sort_order, 0)
        self.assertEqual(first_image.sort_order, 1)
        self.assertEqual(first_image.alt_text, 'Updated first')
        self.assertEqual(second_image.sort_order, 2)

    def test_vendor_can_change_primary_image_when_reordering(self):
        first_image = self.create_product_image(0, is_primary=True)
        second_image = self.create_product_image(1)
        self.client.force_authenticate(user=self.vendor)

        response = self.client.patch(
            self.url,
            {
                'images': [
                    {
                        'id': first_image.id,
                        'sort_order': 1,
                        'is_primary': False,
                    },
                    {
                        'id': second_image.id,
                        'sort_order': 0,
                        'is_primary': True,
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first_image.refresh_from_db()
        second_image.refresh_from_db()
        self.assertFalse(first_image.is_primary)
        self.assertTrue(second_image.is_primary)

    def test_reorder_rejects_duplicate_sort_orders(self):
        first_image = self.create_product_image(0)
        second_image = self.create_product_image(1)
        self.client.force_authenticate(user=self.vendor)

        response = self.client.patch(
            self.url,
            {
                'images': [
                    {'id': first_image.id, 'sort_order': 0},
                    {'id': second_image.id, 'sort_order': 0},
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('sort_order', response.data)

    def test_reorder_rejects_images_from_other_product(self):
        other_product = Product.all_objects.create(
            tenant=self.tenant,
            name='MacBook Pro',
            slug='macbook-pro',
            sku='MBP-001',
            brand=self.brand,
            category=self.category,
            status='active',
            base_price='1499.00',
            tech_specs={'cpu': 'M3 Pro'},
        )
        other_image = ProductImage.all_objects.create(
            tenant=self.tenant,
            product=other_product,
            image='products/images/other.gif',
            sort_order=0,
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.patch(
            self.url,
            {'images': [{'id': other_image.id, 'sort_order': 0}]},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('images', response.data)

    def test_non_vendor_cannot_reorder_product_images(self):
        product_image = self.create_product_image(0)
        self.client.force_authenticate(user=self.customer)

        response = self.client.patch(
            self.url,
            {'images': [{'id': product_image.id, 'sort_order': 1}]},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendor_can_delete_product_image(self):
        product_image = self.create_product_image(0)
        self.client.force_authenticate(user=self.vendor)

        response = self.client.delete(
            reverse(
                'product-image-delete',
                kwargs={
                    'slug': self.product.slug,
                    'image_id': product_image.id,
                },
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            ProductImage.all_objects.filter(id=product_image.id).exists()
        )

    def test_non_vendor_cannot_delete_product_image(self):
        product_image = self.create_product_image(0)
        self.client.force_authenticate(user=self.customer)

        response = self.client.delete(
            reverse(
                'product-image-delete',
                kwargs={
                    'slug': self.product.slug,
                    'image_id': product_image.id,
                },
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(
            ProductImage.all_objects.filter(id=product_image.id).exists()
        )

    def test_vendor_cannot_delete_image_from_other_product(self):
        other_product = Product.all_objects.create(
            tenant=self.tenant,
            name='MacBook Pro',
            slug='macbook-pro-delete',
            sku='MBP-DELETE-001',
            brand=self.brand,
            category=self.category,
            status='active',
            base_price='1499.00',
            tech_specs={'cpu': 'M3 Pro'},
        )
        other_image = ProductImage.all_objects.create(
            tenant=self.tenant,
            product=other_product,
            image='products/images/other-delete.gif',
            sort_order=0,
        )
        self.client.force_authenticate(user=self.vendor)

        response = self.client.delete(
            reverse(
                'product-image-delete',
                kwargs={
                    'slug': self.product.slug,
                    'image_id': other_image.id,
                },
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(
            ProductImage.all_objects.filter(id=other_image.id).exists()
        )
