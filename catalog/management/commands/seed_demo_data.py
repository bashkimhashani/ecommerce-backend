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
    {'name': 'HP', 'slug': 'hp', 'country_of_origin': 'United States'},
    {'name': 'ASUS', 'slug': 'asus', 'country_of_origin': 'Taiwan'},
    {'name': 'Acer', 'slug': 'acer', 'country_of_origin': 'Taiwan'},
    {'name': 'Canon', 'slug': 'canon', 'country_of_origin': 'Japan'},
    {'name': 'Epson', 'slug': 'epson', 'country_of_origin': 'Japan'},
    {'name': 'Brother', 'slug': 'brother', 'country_of_origin': 'Japan'},
    {'name': 'Intel', 'slug': 'intel', 'country_of_origin': 'United States'},
    {'name': 'AMD', 'slug': 'amd', 'country_of_origin': 'United States'},
    {'name': 'NVIDIA', 'slug': 'nvidia', 'country_of_origin': 'United States'},
    {'name': 'Corsair', 'slug': 'corsair', 'country_of_origin': 'United States'},
    {'name': 'TP-Link', 'slug': 'tp-link', 'country_of_origin': 'China'},
    {'name': 'Netgear', 'slug': 'netgear', 'country_of_origin': 'United States'},
    {'name': 'TechCare', 'slug': 'techcare', 'country_of_origin': 'United States'},
    {'name': 'Sony', 'slug': 'sony', 'country_of_origin': 'Japan'},
    {'name': 'Logitech', 'slug': 'logitech', 'country_of_origin': 'Switzerland'},
]

CATEGORIES = [
    {'name': 'Computers', 'slug': 'computers'},
    {'name': 'Laptops', 'slug': 'laptops', 'parent': 'computers'},
    {'name': 'Desktop PCs', 'slug': 'desktop-pcs', 'parent': 'computers'},
    {'name': 'PC Parts', 'slug': 'pc-parts', 'parent': 'computers'},
    {'name': 'Phones', 'slug': 'phones'},
    {'name': 'Smartphones', 'slug': 'smartphones', 'parent': 'phones'},
    {'name': 'Networking', 'slug': 'networking'},
    {'name': 'Printers', 'slug': 'printers'},
    {'name': 'Repairs', 'slug': 'repairs'},
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
        'name': 'Dell OptiPlex 7010 Desktop',
        'slug': 'dell-optiplex-7010-desktop',
        'sku': 'OPT7010-I5-512',
        'brand': 'dell',
        'category': 'desktop-pcs',
        'base_price': Decimal('749.00'),
        'description': 'Compact business desktop PC for office workflows.',
        'tech_specs': {
            'cpu': 'Intel Core i5',
            'ram': '16GB',
            'storage': '512GB SSD',
            'form_factor': 'Small Form Factor',
        },
        'variants': [
            {'color': 'Black', 'storage': '512GB', 'ram': '16GB', 'price': Decimal('749.00'), 'stock': 18},
            {'color': 'Black', 'storage': '1TB', 'ram': '32GB', 'price': Decimal('949.00'), 'stock': 8},
        ],
    },
    {
        'name': 'HP Envy Desktop TE02',
        'slug': 'hp-envy-desktop-te02',
        'sku': 'HPENVY-TE02-I7',
        'brand': 'hp',
        'category': 'desktop-pcs',
        'base_price': Decimal('1199.99'),
        'description': 'Creator-ready desktop with dedicated graphics options.',
        'tech_specs': {
            'cpu': 'Intel Core i7',
            'ram': '16GB',
            'storage': '1TB SSD',
            'graphics': 'NVIDIA RTX 4060',
        },
        'variants': [
            {'color': 'Natural Silver', 'storage': '1TB', 'ram': '16GB', 'price': Decimal('1199.99'), 'stock': 10},
        ],
    },
    {
        'name': 'ASUS ROG G22CH Gaming Desktop',
        'slug': 'asus-rog-g22ch-gaming-desktop',
        'sku': 'ROGG22-I7-4070',
        'brand': 'asus',
        'category': 'desktop-pcs',
        'base_price': Decimal('1799.00'),
        'description': 'Small gaming desktop with high-end RTX graphics.',
        'tech_specs': {
            'cpu': 'Intel Core i7',
            'ram': '32GB',
            'storage': '1TB SSD',
            'graphics': 'NVIDIA RTX 4070',
        },
        'variants': [
            {'color': 'Eclipse Gray', 'storage': '1TB', 'ram': '32GB', 'price': Decimal('1799.00'), 'stock': 5},
        ],
    },
    {
        'name': 'TP-Link Archer AXE75 Wi-Fi 6E Router',
        'slug': 'tp-link-archer-axe75-wifi-6e-router',
        'sku': 'ARCHER-AXE75',
        'brand': 'tp-link',
        'category': 'networking',
        'base_price': Decimal('199.99'),
        'description': 'Tri-band Wi-Fi 6E router for fast home networks.',
        'tech_specs': {
            'wifi': 'Wi-Fi 6E',
            'bands': 'Tri-band',
            'ports': 'Gigabit WAN/LAN',
            'coverage': 'Up to 2900 sq ft',
        },
        'variants': [
            {'color': 'Black', 'storage': '', 'ram': '', 'price': Decimal('199.99'), 'stock': 21},
        ],
    },
    {
        'name': 'Netgear Nighthawk RAXE300 Router',
        'slug': 'netgear-nighthawk-raxe300-router',
        'sku': 'RAXE300-WIFI6E',
        'brand': 'netgear',
        'category': 'networking',
        'base_price': Decimal('349.99'),
        'description': 'High-performance Wi-Fi 6E router for gaming and streaming.',
        'tech_specs': {
            'wifi': 'Wi-Fi 6E',
            'speed': 'Up to 7.8Gbps',
            'ports': '2.5GbE plus Gigabit LAN',
            'coverage': 'Up to 2500 sq ft',
        },
        'variants': [
            {'color': 'Black', 'storage': '', 'ram': '', 'price': Decimal('349.99'), 'stock': 12},
        ],
    },
    {
        'name': 'TP-Link TL-SG108 8-Port Gigabit Switch',
        'slug': 'tp-link-tl-sg108-8-port-gigabit-switch',
        'sku': 'TLSG108-8PORT',
        'brand': 'tp-link',
        'category': 'networking',
        'base_price': Decimal('29.99'),
        'description': 'Unmanaged metal desktop switch for simple wired expansion.',
        'tech_specs': {
            'ports': '8 Gigabit Ethernet',
            'type': 'Unmanaged',
            'case': 'Metal',
            'mounting': 'Desktop or wall',
        },
        'variants': [
            {'color': 'Blue', 'storage': '', 'ram': '', 'price': Decimal('29.99'), 'stock': 40},
        ],
    },
    {
        'name': 'Canon PIXMA TR8620a All-in-One Printer',
        'slug': 'canon-pixma-tr8620a-all-in-one-printer',
        'sku': 'PIXMA-TR8620A',
        'brand': 'canon',
        'category': 'printers',
        'base_price': Decimal('179.99'),
        'description': 'Wireless color all-in-one printer for home offices.',
        'tech_specs': {
            'type': 'Inkjet all-in-one',
            'functions': 'Print, copy, scan, fax',
            'connectivity': 'Wi-Fi, USB',
            'duplex': True,
        },
        'variants': [
            {'color': 'Black', 'storage': '', 'ram': '', 'price': Decimal('179.99'), 'stock': 17},
        ],
    },
    {
        'name': 'Epson EcoTank ET-2850 Printer',
        'slug': 'epson-ecotank-et-2850-printer',
        'sku': 'ECOTANK-ET2850',
        'brand': 'epson',
        'category': 'printers',
        'base_price': Decimal('299.99'),
        'description': 'Cartridge-free all-in-one printer with refillable ink tanks.',
        'tech_specs': {
            'type': 'Ink tank all-in-one',
            'functions': 'Print, copy, scan',
            'connectivity': 'Wi-Fi, USB',
            'duplex': True,
        },
        'variants': [
            {'color': 'White', 'storage': '', 'ram': '', 'price': Decimal('299.99'), 'stock': 13},
        ],
    },
    {
        'name': 'Brother HL-L2460DW Laser Printer',
        'slug': 'brother-hl-l2460dw-laser-printer',
        'sku': 'HLL2460DW-LASER',
        'brand': 'brother',
        'category': 'printers',
        'base_price': Decimal('159.99'),
        'description': 'Compact monochrome laser printer for fast documents.',
        'tech_specs': {
            'type': 'Monochrome laser',
            'speed': 'Up to 36 ppm',
            'connectivity': 'Wi-Fi, Ethernet, USB',
            'duplex': True,
        },
        'variants': [
            {'color': 'Gray', 'storage': '', 'ram': '', 'price': Decimal('159.99'), 'stock': 20},
        ],
    },
    {
        'name': 'Intel Core i7-14700K Processor',
        'slug': 'intel-core-i7-14700k-processor',
        'sku': 'I7-14700K',
        'brand': 'intel',
        'category': 'pc-parts',
        'base_price': Decimal('409.99'),
        'description': 'Unlocked desktop CPU for gaming and productivity builds.',
        'tech_specs': {
            'socket': 'LGA1700',
            'cores': '20 cores',
            'threads': '28 threads',
            'boost_clock': 'Up to 5.6GHz',
        },
        'variants': [
            {'color': '', 'storage': '', 'ram': '', 'price': Decimal('409.99'), 'stock': 15},
        ],
    },
    {
        'name': 'AMD Ryzen 7 7800X3D Processor',
        'slug': 'amd-ryzen-7-7800x3d-processor',
        'sku': 'RYZEN7-7800X3D',
        'brand': 'amd',
        'category': 'pc-parts',
        'base_price': Decimal('379.99'),
        'description': 'Gaming-focused desktop CPU with 3D V-Cache.',
        'tech_specs': {
            'socket': 'AM5',
            'cores': '8 cores',
            'threads': '16 threads',
            'cache': '96MB L3',
        },
        'variants': [
            {'color': '', 'storage': '', 'ram': '', 'price': Decimal('379.99'), 'stock': 14},
        ],
    },
    {
        'name': 'NVIDIA GeForce RTX 4070 SUPER',
        'slug': 'nvidia-geforce-rtx-4070-super',
        'sku': 'RTX4070S-12GB',
        'brand': 'nvidia',
        'category': 'pc-parts',
        'base_price': Decimal('599.99'),
        'description': '12GB graphics card for high-refresh 1440p gaming.',
        'tech_specs': {
            'vram': '12GB GDDR6X',
            'architecture': 'Ada Lovelace',
            'ray_tracing': True,
            'recommended_psu': '650W',
        },
        'variants': [
            {'color': 'Black', 'storage': '', 'ram': '12GB', 'price': Decimal('599.99'), 'stock': 9},
        ],
    },
    {
        'name': 'Corsair Vengeance DDR5 32GB Kit',
        'slug': 'corsair-vengeance-ddr5-32gb-kit',
        'sku': 'VEN-DDR5-32GB',
        'brand': 'corsair',
        'category': 'pc-parts',
        'base_price': Decimal('109.99'),
        'description': 'Two-stick DDR5 memory kit for modern desktop builds.',
        'tech_specs': {
            'capacity': '32GB',
            'speed': '6000MT/s',
            'kit': '2 x 16GB',
            'type': 'DDR5',
        },
        'variants': [
            {'color': 'Black', 'storage': '', 'ram': '32GB', 'price': Decimal('109.99'), 'stock': 28},
            {'color': 'White', 'storage': '', 'ram': '32GB', 'price': Decimal('114.99'), 'stock': 16},
        ],
    },
    {
        'name': 'Laptop Screen Replacement Service',
        'slug': 'laptop-screen-replacement-service',
        'sku': 'REPAIR-LAPTOP-SCREEN',
        'brand': 'techcare',
        'category': 'repairs',
        'base_price': Decimal('149.99'),
        'description': 'Screen replacement service for common 13-inch to 16-inch laptops.',
        'tech_specs': {
            'service_type': 'Laptop repair',
            'turnaround': '2-4 business days',
            'warranty': '90 days',
            'diagnostics_included': True,
        },
        'variants': [
            {'color': 'Standard Panel', 'storage': '', 'ram': '', 'price': Decimal('149.99'), 'stock': 25},
            {'color': 'Premium Panel', 'storage': '', 'ram': '', 'price': Decimal('229.99'), 'stock': 10},
        ],
    },
    {
        'name': 'Desktop PC Diagnostic and Tune-Up',
        'slug': 'desktop-pc-diagnostic-and-tune-up',
        'sku': 'REPAIR-DESKTOP-DIAG',
        'brand': 'techcare',
        'category': 'repairs',
        'base_price': Decimal('79.99'),
        'description': 'Hardware diagnostics, cleanup, and performance tune-up for desktop PCs.',
        'tech_specs': {
            'service_type': 'Desktop repair',
            'turnaround': '1-2 business days',
            'warranty': '30 days',
            'includes_cleaning': True,
        },
        'variants': [
            {'color': 'Standard', 'storage': '', 'ram': '', 'price': Decimal('79.99'), 'stock': 30},
        ],
    },
    {
        'name': 'Printer Setup and Repair Service',
        'slug': 'printer-setup-and-repair-service',
        'sku': 'REPAIR-PRINTER-SETUP',
        'brand': 'techcare',
        'category': 'repairs',
        'base_price': Decimal('59.99'),
        'description': 'Printer setup, driver installation, paper-feed checks, and basic repair.',
        'tech_specs': {
            'service_type': 'Printer support',
            'turnaround': 'Same day',
            'warranty': '30 days',
            'remote_available': True,
        },
        'variants': [
            {'color': 'Remote', 'storage': '', 'ram': '', 'price': Decimal('59.99'), 'stock': 40},
            {'color': 'In-store', 'storage': '', 'ram': '', 'price': Decimal('89.99'), 'stock': 20},
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
