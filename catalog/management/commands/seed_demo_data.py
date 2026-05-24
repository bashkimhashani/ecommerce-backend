from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from cart.models import Cart, CartItem
from catalog.models import Brand, Category, Product, ProductVariant
from checkout.models import CheckoutSession
from inventory.models import Inventory
from orders.models import Order, OrderEvent, OrderItem
from tenants.models import Tenant
from vendor.models import VendorProfile


TENANT_DATA = {
    'name': 'Demo Tech Store',
    'slug': 'demo-tech-store',
    'domain': 'demo-tech-store.local',
    'plan': 'premium',
    'is_active': True,
}

DEMO_PASSWORD = 'DemoPass123!'

BRANDS = [
    {'name': 'Apple', 'slug': 'apple', 'country_of_origin': 'United States'},
    {'name': 'Samsung', 'slug': 'samsung', 'country_of_origin': 'South Korea'},
    {'name': 'Dell', 'slug': 'dell', 'country_of_origin': 'United States'},
    {'name': 'Lenovo', 'slug': 'lenovo', 'country_of_origin': 'China'},
    {'name': 'Sony', 'slug': 'sony', 'country_of_origin': 'Japan'},
    {'name': 'Logitech', 'slug': 'logitech', 'country_of_origin': 'Switzerland'},
]

CATEGORIES = [
    {'name': 'Computers', 'slug': 'computers'},
    {'name': 'Laptops', 'slug': 'laptops', 'parent': 'computers'},
    {'name': 'Phones', 'slug': 'phones'},
    {'name': 'Smartphones', 'slug': 'smartphones', 'parent': 'phones'},
    {'name': 'Gaming', 'slug': 'gaming'},
    {'name': 'Accessories', 'slug': 'accessories'},
    {'name': 'Audio', 'slug': 'audio'},
]

PRODUCTS = [
    {
        'name': 'Apple MacBook Air 13 M3',
        'slug': 'apple-macbook-air-13-m3',
        'sku': 'MBA13-M3-256',
        'brand': 'apple',
        'category': 'laptops',
        'base_price': Decimal('1099.00'),
        'description': 'Lightweight laptop with Apple M3 performance.',
        'tech_specs': {
            'cpu': 'Apple M3',
            'ram': '8GB',
            'storage': '256GB SSD',
            'display': '13.6-inch Liquid Retina',
        },
        'variants': [
            {'color': 'Midnight', 'storage': '256GB', 'ram': '8GB', 'price': Decimal('1099.00'), 'stock': 18},
            {'color': 'Silver', 'storage': '512GB', 'ram': '16GB', 'price': Decimal('1399.00'), 'stock': 9},
        ],
    },
    {
        'name': 'Apple iPhone 15 Pro',
        'slug': 'apple-iphone-15-pro',
        'sku': 'IPH15P-128',
        'brand': 'apple',
        'category': 'smartphones',
        'base_price': Decimal('999.00'),
        'description': 'Premium smartphone with A17 Pro and titanium design.',
        'tech_specs': {
            'chip': 'A17 Pro',
            'storage': '128GB',
            'display': '6.1-inch Super Retina XDR',
            'camera': '48MP main',
        },
        'variants': [
            {'color': 'Natural Titanium', 'storage': '128GB', 'ram': '', 'price': Decimal('999.00'), 'stock': 22},
            {'color': 'Blue Titanium', 'storage': '256GB', 'ram': '', 'price': Decimal('1099.00'), 'stock': 14},
        ],
    },
    {
        'name': 'Samsung Galaxy S24 Ultra',
        'slug': 'samsung-galaxy-s24-ultra',
        'sku': 'SGS24U-256',
        'brand': 'samsung',
        'category': 'smartphones',
        'base_price': Decimal('1199.99'),
        'description': 'Large-screen Android flagship for power users.',
        'tech_specs': {
            'processor': 'Snapdragon 8 Gen 3',
            'ram': '12GB',
            'storage': '256GB',
            'display': '6.8-inch AMOLED',
        },
        'variants': [
            {'color': 'Titanium Gray', 'storage': '256GB', 'ram': '12GB', 'price': Decimal('1199.99'), 'stock': 16},
            {'color': 'Titanium Black', 'storage': '512GB', 'ram': '12GB', 'price': Decimal('1419.99'), 'stock': 7},
        ],
    },
    {
        'name': 'Dell XPS 13 Plus',
        'slug': 'dell-xps-13-plus',
        'sku': 'DXPS13P-I7-512',
        'brand': 'dell',
        'category': 'laptops',
        'base_price': Decimal('1299.00'),
        'description': 'Compact Windows ultrabook with a premium display.',
        'tech_specs': {
            'cpu': 'Intel Core i7',
            'ram': '16GB',
            'storage': '512GB SSD',
            'display': '13.4-inch FHD+',
        },
        'variants': [
            {'color': 'Graphite', 'storage': '512GB', 'ram': '16GB', 'price': Decimal('1299.00'), 'stock': 12},
        ],
    },
    {
        'name': 'Lenovo Legion 5 Gaming Laptop',
        'slug': 'lenovo-legion-5-gaming-laptop',
        'sku': 'LEGION5-R7-4060',
        'brand': 'lenovo',
        'category': 'gaming',
        'base_price': Decimal('1399.00'),
        'description': 'Gaming laptop with RTX graphics and high-refresh display.',
        'tech_specs': {
            'cpu': 'AMD Ryzen 7',
            'gpu': 'NVIDIA RTX 4060',
            'ram': '16GB',
            'storage': '1TB SSD',
        },
        'variants': [
            {'color': 'Storm Grey', 'storage': '1TB', 'ram': '16GB', 'price': Decimal('1399.00'), 'stock': 6},
        ],
    },
    {
        'name': 'Sony WH-1000XM5 Headphones',
        'slug': 'sony-wh-1000xm5-headphones',
        'sku': 'WH1000XM5-BLK',
        'brand': 'sony',
        'category': 'audio',
        'base_price': Decimal('399.99'),
        'description': 'Noise-cancelling wireless headphones for travel and work.',
        'tech_specs': {
            'type': 'over-ear',
            'noise_cancelling': True,
            'battery_life': '30 hours',
            'connectivity': 'Bluetooth',
        },
        'variants': [
            {'color': 'Black', 'storage': '', 'ram': '', 'price': Decimal('399.99'), 'stock': 24},
            {'color': 'Silver', 'storage': '', 'ram': '', 'price': Decimal('399.99'), 'stock': 11},
        ],
    },
    {
        'name': 'Logitech MX Master 3S',
        'slug': 'logitech-mx-master-3s',
        'sku': 'MXM3S-GRAPHITE',
        'brand': 'logitech',
        'category': 'accessories',
        'base_price': Decimal('99.99'),
        'description': 'Ergonomic wireless mouse for productivity setups.',
        'tech_specs': {
            'type': 'wireless mouse',
            'dpi': '8000',
            'connectivity': 'Bluetooth/Logi Bolt',
            'battery_life': '70 days',
        },
        'variants': [
            {'color': 'Graphite', 'storage': '', 'ram': '', 'price': Decimal('99.99'), 'stock': 35},
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed a complete, repeatable demo database for local development.'

    def handle(self, *args, **options):
        with transaction.atomic():
            tenant = self.seed_tenant()
            users = self.seed_users(tenant)
            self.seed_vendor_profile(tenant, users['vendor'])
            products = self.seed_catalog(tenant)
            variants = self.seed_variants(tenant, products)
            vendor = self.seed_inventory(tenant, users['vendor'], variants)
            cart = self.seed_cart(tenant, users['customer'], variants)
            self.seed_order(tenant, users['customer'], cart, variants)
            tenant.owner = users['admin']
            tenant.save(update_fields=['owner', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(
            'Demo database is ready. '
            f'Users: admin@example.com, vendor@example.com, customer@example.com. '
            f'Password for all demo users: {DEMO_PASSWORD}'
        ))

    def seed_tenant(self):
        tenant, _ = Tenant.objects.update_or_create(
            slug=TENANT_DATA['slug'],
            defaults=TENANT_DATA,
        )
        return tenant

    def seed_users(self, tenant):
        User = get_user_model()
        users = {
            'admin': {
                'email': 'admin@example.com',
                'first_name': 'Demo',
                'last_name': 'Admin',
                'role': 'superadmin',
                'is_staff': True,
                'is_superuser': True,
            },
            'vendor': {
                'email': 'vendor@example.com',
                'first_name': 'Demo',
                'last_name': 'Vendor',
                'role': 'vendor_admin',
                'is_staff': True,
                'is_superuser': False,
            },
            'customer': {
                'email': 'customer@example.com',
                'first_name': 'Demo',
                'last_name': 'Customer',
                'role': 'customer',
                'is_staff': False,
                'is_superuser': False,
            },
        }

        created = {}
        for key, user_data in users.items():
            user, was_created = User.objects.update_or_create(
                email=user_data['email'],
                defaults={
                    **user_data,
                    'tenant': tenant,
                    'is_active': True,
                    'is_email_verified': True,
                },
            )
            if was_created or not user.check_password(DEMO_PASSWORD):
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=['password'])
            created[key] = user

        vendor_group = Group.objects.filter(name='vendor_admin').first()
        if vendor_group:
            created['vendor'].groups.add(vendor_group)

        return created

    def seed_vendor_profile(self, tenant, user):
        return VendorProfile.objects.update_or_create(
            user=user,
            tenant=tenant,
            defaults={
                'store_name': 'Demo Tech Vendor',
                'store_description': 'Local demo vendor for electronics.',
                'contact_email': user.email,
                'contact_phone': '+15550101010',
                'is_active': True,
                'rating': 4.8,
                'total_sales': Decimal('3499.97'),
            },
        )[0]

    def seed_catalog(self, tenant):
        brands = {}
        for brand_data in BRANDS:
            brand, _ = Brand.objects.update_or_create(
                tenant=tenant,
                slug=brand_data['slug'],
                defaults={
                    'name': brand_data['name'],
                    'country_of_origin': brand_data['country_of_origin'],
                },
            )
            brands[brand_data['slug']] = brand

        categories = {}
        for category_data in CATEGORIES:
            parent = categories.get(category_data.get('parent'))
            category, _ = Category.all_objects.update_or_create(
                tenant=tenant,
                slug=category_data['slug'],
                defaults={
                    'name': category_data['name'],
                    'parent': parent,
                    'is_active': True,
                },
            )
            categories[category_data['slug']] = category
        Category.objects.rebuild()

        products = {}
        for product_data in PRODUCTS:
            product, _ = Product.objects.update_or_create(
                tenant=tenant,
                sku=product_data['sku'],
                defaults={
                    'name': product_data['name'],
                    'slug': product_data['slug'],
                    'description': product_data['description'],
                    'brand': brands[product_data['brand']],
                    'category': categories[product_data['category']],
                    'status': Product.Status.ACTIVE,
                    'base_price': product_data['base_price'],
                    'tech_specs': product_data['tech_specs'],
                },
            )
            products[product_data['sku']] = product
        return products

    def seed_variants(self, tenant, products):
        variants = []
        for product_data in PRODUCTS:
            product = products[product_data['sku']]
            for variant_data in product_data['variants']:
                variant, _ = ProductVariant.objects.update_or_create(
                    tenant=tenant,
                    product=product,
                    color=variant_data['color'],
                    storage=variant_data['storage'],
                    ram=variant_data['ram'],
                    defaults={
                        'variant_price': variant_data['price'],
                        'stock_quantity': variant_data['stock'],
                    },
                )
                variants.append(variant)

        product_ids_with_variants = ProductVariant.objects.filter(
            tenant=tenant,
        ).values_list('product_id', flat=True)
        products_without_variants = Product.all_objects.filter(
            tenant=tenant,
            status=Product.Status.ACTIVE,
        ).exclude(id__in=product_ids_with_variants)

        for product in products_without_variants:
            variant, _ = ProductVariant.objects.update_or_create(
                tenant=tenant,
                product=product,
                color='Default',
                storage='',
                ram='',
                defaults={
                    'variant_price': product.base_price,
                    'stock_quantity': 20,
                },
            )
            variants.append(variant)
        return variants

    def seed_inventory(self, tenant, user, variants):
        vendor = VendorProfile.objects.get(user=user, tenant=tenant)
        for variant in variants:
            Inventory.objects.update_or_create(
                tenant=tenant,
                product_variant=variant,
                defaults={
                    'vendor': vendor,
                    'quantity': variant.stock_quantity,
                    'low_stock_threshold': 10,
                },
            )
        return vendor

    def seed_cart(self, tenant, user, variants):
        active_cart, _ = Cart.objects.update_or_create(
            user=user,
            status=Cart.Status.ACTIVE,
            defaults={'tenant': tenant},
        )
        CartItem.objects.filter(cart=active_cart).delete()
        for variant in variants[:2]:
            CartItem.objects.create(
                tenant=tenant,
                cart=active_cart,
                product_variant=variant,
                quantity=1,
                unit_price=variant.variant_price,
            )
        return active_cart

    def seed_order(self, tenant, user, active_cart, variants):
        order_cart, _ = Cart.objects.update_or_create(
            session_key='demo-order-cart',
            status=Cart.Status.CHECKED_OUT,
            defaults={'tenant': tenant},
        )
        CartItem.objects.filter(cart=order_cart).delete()

        order_variants = variants[2:4]
        for variant in order_variants:
            CartItem.objects.create(
                tenant=tenant,
                cart=order_cart,
                product_variant=variant,
                quantity=1,
                unit_price=variant.variant_price,
            )

        checkout_session, _ = CheckoutSession.objects.update_or_create(
            tenant=tenant,
            idempotency_key='demo-checkout-session-001',
            defaults={
                'user': user,
                'cart': order_cart,
                'status': CheckoutSession.Status.COMPLETED,
                'shipping_address': {
                    'full_name': user.get_full_name(),
                    'line1': '100 Demo Street',
                    'city': 'Budapest',
                    'postal_code': '1051',
                    'country': 'HU',
                },
            },
        )

        order, _ = Order.objects.update_or_create(
            checkout_session=checkout_session,
            defaults={
                'tenant': tenant,
                'user': user,
                'shipping_address': checkout_session.shipping_address,
                'subtotal': order_cart.subtotal,
                'total_amount': order_cart.subtotal,
            },
        )
        Order.objects.filter(pk=order.pk).update(status=Order.Status.CONFIRMED)
        OrderItem.objects.filter(order=order).delete()
        for cart_item in CartItem.objects.filter(cart=order_cart):
            variant = cart_item.product_variant
            variant_label = ', '.join(
                value for value in [variant.color, variant.storage, variant.ram]
                if value
            )
            OrderItem.objects.create(
                tenant=tenant,
                order=order,
                product_variant=variant,
                product_name=variant.product.name,
                variant_label=variant_label,
                quantity=cart_item.quantity,
                unit_price=cart_item.unit_price,
                line_total=cart_item.line_total,
            )

        OrderEvent.objects.update_or_create(
            tenant=tenant,
            order=order,
            transition='seed_demo_data',
            defaults={
                'from_status': Order.Status.PENDING,
                'to_status': Order.Status.CONFIRMED,
                'note': 'Created by the demo seed command.',
            },
        )
        return order
