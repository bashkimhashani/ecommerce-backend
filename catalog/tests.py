import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
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
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], active_product.id)
        self.assertEqual(response.data[0]['name'], 'MacBook Air')
        self.assertEqual(response.data[0]['price'], '999.00')

    def test_product_list_endpoint_response_uses_lightweight_shape(self):
        self.create_product()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data[0].keys()),
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
            [product['id'] for product in response.data],
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
            response.data[0]['thumbnail'],
            'http://testserver/media/products/images/generated/'
            'macbook_thumbnail.jpg',
        )


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
