import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from tenants.models import Tenant

from .models import Brand, Category, Product, ProductImage


User = get_user_model()


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

    def image_upload(self, name='product.gif'):
        return SimpleUploadedFile(
            name,
            (
                b'GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00'
                b'\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00'
                b'\x00\x02\x02D\x01\x00;'
            ),
            content_type='image/gif',
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
