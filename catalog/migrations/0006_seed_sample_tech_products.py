from decimal import Decimal

from django.db import migrations


DEV_TENANT = {
    'name': 'Demo Tech Store',
    'slug': 'demo-tech-store',
    'domain': 'demo-tech-store.local',
    'plan': 'premium',
    'is_active': True,
}

BRANDS = [
    {'name': 'Apple', 'slug': 'apple', 'country_of_origin': 'United States'},
    {'name': 'Samsung', 'slug': 'samsung', 'country_of_origin': 'South Korea'},
    {'name': 'Dell', 'slug': 'dell', 'country_of_origin': 'United States'},
    {'name': 'Lenovo', 'slug': 'lenovo', 'country_of_origin': 'China'},
    {'name': 'HP', 'slug': 'hp', 'country_of_origin': 'United States'},
    {'name': 'ASUS', 'slug': 'asus', 'country_of_origin': 'Taiwan'},
    {'name': 'Sony', 'slug': 'sony', 'country_of_origin': 'Japan'},
    {'name': 'Logitech', 'slug': 'logitech', 'country_of_origin': 'Switzerland'},
    {'name': 'Microsoft', 'slug': 'microsoft', 'country_of_origin': 'United States'},
    {'name': 'Acer', 'slug': 'acer', 'country_of_origin': 'Taiwan'},
]

CATEGORIES = [
    {'name': 'Laptops', 'slug': 'laptops'},
    {'name': 'Smartphones', 'slug': 'smartphones'},
    {'name': 'Tablets', 'slug': 'tablets'},
    {'name': 'Monitors', 'slug': 'monitors'},
    {'name': 'Accessories', 'slug': 'accessories'},
    {'name': 'Gaming', 'slug': 'gaming'},
    {'name': 'Audio', 'slug': 'audio'},
    {'name': 'Networking', 'slug': 'networking'},
]

PRODUCTS = [
    {
        'name': 'Apple MacBook Air 13 M3',
        'slug': 'apple-macbook-air-13-m3',
        'sku': 'MBA13-M3-256',
        'brand': 'apple',
        'category': 'laptops',
        'base_price': Decimal('1099.00'),
        'tech_specs': {'cpu': 'Apple M3', 'ram': '8GB', 'storage': '256GB SSD', 'display': '13.6-inch Liquid Retina'},
    },
    {
        'name': 'Apple iPhone 15 Pro',
        'slug': 'apple-iphone-15-pro',
        'sku': 'IPH15P-128',
        'brand': 'apple',
        'category': 'smartphones',
        'base_price': Decimal('999.00'),
        'tech_specs': {'chip': 'A17 Pro', 'storage': '128GB', 'display': '6.1-inch Super Retina XDR', 'camera': '48MP main'},
    },
    {
        'name': 'Samsung Galaxy S24 Ultra',
        'slug': 'samsung-galaxy-s24-ultra',
        'sku': 'SGS24U-256',
        'brand': 'samsung',
        'category': 'smartphones',
        'base_price': Decimal('1199.99'),
        'tech_specs': {'processor': 'Snapdragon 8 Gen 3', 'ram': '12GB', 'storage': '256GB', 'display': '6.8-inch AMOLED'},
    },
    {
        'name': 'Samsung Galaxy Tab S9',
        'slug': 'samsung-galaxy-tab-s9',
        'sku': 'SGTS9-128',
        'brand': 'samsung',
        'category': 'tablets',
        'base_price': Decimal('799.99'),
        'tech_specs': {'processor': 'Snapdragon 8 Gen 2', 'ram': '8GB', 'storage': '128GB', 'display': '11-inch AMOLED'},
    },
    {
        'name': 'Dell XPS 13 Plus',
        'slug': 'dell-xps-13-plus',
        'sku': 'DXPS13P-I7-512',
        'brand': 'dell',
        'category': 'laptops',
        'base_price': Decimal('1299.00'),
        'tech_specs': {'cpu': 'Intel Core i7', 'ram': '16GB', 'storage': '512GB SSD', 'display': '13.4-inch FHD+'},
    },
    {
        'name': 'Dell UltraSharp 27 4K Monitor',
        'slug': 'dell-ultrasharp-27-4k-monitor',
        'sku': 'DU2724-4K',
        'brand': 'dell',
        'category': 'monitors',
        'base_price': Decimal('549.99'),
        'tech_specs': {'size': '27-inch', 'resolution': '3840x2160', 'panel': 'IPS', 'refresh_rate': '60Hz'},
    },
    {
        'name': 'Lenovo ThinkPad X1 Carbon Gen 12',
        'slug': 'lenovo-thinkpad-x1-carbon-gen-12',
        'sku': 'TPX1C-G12-1TB',
        'brand': 'lenovo',
        'category': 'laptops',
        'base_price': Decimal('1799.00'),
        'tech_specs': {'cpu': 'Intel Core Ultra 7', 'ram': '32GB', 'storage': '1TB SSD', 'weight': '1.09kg'},
    },
    {
        'name': 'Lenovo Legion 5 Gaming Laptop',
        'slug': 'lenovo-legion-5-gaming-laptop',
        'sku': 'LEGION5-R7-4060',
        'brand': 'lenovo',
        'category': 'gaming',
        'base_price': Decimal('1399.00'),
        'tech_specs': {'cpu': 'AMD Ryzen 7', 'gpu': 'NVIDIA RTX 4060', 'ram': '16GB', 'storage': '1TB SSD'},
    },
    {
        'name': 'HP Spectre x360 14',
        'slug': 'hp-spectre-x360-14',
        'sku': 'HPSX360-14-512',
        'brand': 'hp',
        'category': 'laptops',
        'base_price': Decimal('1249.99'),
        'tech_specs': {'cpu': 'Intel Core Ultra 5', 'ram': '16GB', 'storage': '512GB SSD', 'display': '14-inch OLED touch'},
    },
    {
        'name': 'HP Omen 27q Gaming Monitor',
        'slug': 'hp-omen-27q-gaming-monitor',
        'sku': 'OMEN27Q-QHD',
        'brand': 'hp',
        'category': 'monitors',
        'base_price': Decimal('299.99'),
        'tech_specs': {'size': '27-inch', 'resolution': '2560x1440', 'refresh_rate': '165Hz', 'panel': 'IPS'},
    },
    {
        'name': 'ASUS ROG Strix G16',
        'slug': 'asus-rog-strix-g16',
        'sku': 'ROGG16-I9-4070',
        'brand': 'asus',
        'category': 'gaming',
        'base_price': Decimal('1899.00'),
        'tech_specs': {'cpu': 'Intel Core i9', 'gpu': 'NVIDIA RTX 4070', 'ram': '16GB', 'display': '16-inch 240Hz'},
    },
    {
        'name': 'ASUS ZenScreen Portable Monitor',
        'slug': 'asus-zenscreen-portable-monitor',
        'sku': 'ZSCREEN-15-FHD',
        'brand': 'asus',
        'category': 'monitors',
        'base_price': Decimal('219.99'),
        'tech_specs': {'size': '15.6-inch', 'resolution': '1920x1080', 'connectivity': 'USB-C', 'weight': '0.78kg'},
    },
    {
        'name': 'Sony WH-1000XM5 Headphones',
        'slug': 'sony-wh-1000xm5-headphones',
        'sku': 'WH1000XM5-BLK',
        'brand': 'sony',
        'category': 'audio',
        'base_price': Decimal('399.99'),
        'tech_specs': {'type': 'over-ear', 'noise_cancelling': True, 'battery_life': '30 hours', 'connectivity': 'Bluetooth'},
    },
    {
        'name': 'Sony PlayStation 5 Slim',
        'slug': 'sony-playstation-5-slim',
        'sku': 'PS5-SLIM-1TB',
        'brand': 'sony',
        'category': 'gaming',
        'base_price': Decimal('499.99'),
        'tech_specs': {'storage': '1TB SSD', 'resolution': 'up to 4K', 'ray_tracing': True, 'edition': 'disc'},
    },
    {
        'name': 'Logitech MX Master 3S',
        'slug': 'logitech-mx-master-3s',
        'sku': 'MXM3S-GRAPHITE',
        'brand': 'logitech',
        'category': 'accessories',
        'base_price': Decimal('99.99'),
        'tech_specs': {'type': 'wireless mouse', 'dpi': '8000', 'connectivity': 'Bluetooth/Logi Bolt', 'battery_life': '70 days'},
    },
    {
        'name': 'Logitech MX Keys S',
        'slug': 'logitech-mx-keys-s',
        'sku': 'MXKEYSS-US',
        'brand': 'logitech',
        'category': 'accessories',
        'base_price': Decimal('109.99'),
        'tech_specs': {'type': 'wireless keyboard', 'layout': 'US', 'backlit': True, 'connectivity': 'Bluetooth/Logi Bolt'},
    },
    {
        'name': 'Microsoft Surface Pro 10',
        'slug': 'microsoft-surface-pro-10',
        'sku': 'SURFPRO10-256',
        'brand': 'microsoft',
        'category': 'tablets',
        'base_price': Decimal('1199.99'),
        'tech_specs': {'cpu': 'Intel Core Ultra 5', 'ram': '16GB', 'storage': '256GB SSD', 'display': '13-inch PixelSense'},
    },
    {
        'name': 'Microsoft Xbox Series X',
        'slug': 'microsoft-xbox-series-x',
        'sku': 'XBOX-SX-1TB',
        'brand': 'microsoft',
        'category': 'gaming',
        'base_price': Decimal('499.99'),
        'tech_specs': {'storage': '1TB SSD', 'resolution': 'up to 4K', 'frame_rate': 'up to 120 FPS', 'drive': '4K UHD Blu-ray'},
    },
    {
        'name': 'Acer Swift Go 14',
        'slug': 'acer-swift-go-14',
        'sku': 'SWIFTGO14-OLED',
        'brand': 'acer',
        'category': 'laptops',
        'base_price': Decimal('899.99'),
        'tech_specs': {'cpu': 'Intel Core Ultra 5', 'ram': '16GB', 'storage': '512GB SSD', 'display': '14-inch OLED'},
    },
    {
        'name': 'Acer Predator Connect W6 Router',
        'slug': 'acer-predator-connect-w6-router',
        'sku': 'PRED-W6-WIFI6E',
        'brand': 'acer',
        'category': 'networking',
        'base_price': Decimal('299.99'),
        'tech_specs': {'wifi': 'Wi-Fi 6E', 'bands': 'tri-band', 'ports': '2.5GbE WAN/LAN', 'gaming_qos': True},
    },
]


def seed_sample_tech_products(apps, schema_editor):
    Tenant = apps.get_model('tenants', 'Tenant')
    Brand = apps.get_model('catalog', 'Brand')
    Category = apps.get_model('catalog', 'Category')
    Product = apps.get_model('catalog', 'Product')

    tenant, _ = Tenant.objects.get_or_create(
        slug=DEV_TENANT['slug'],
        defaults=DEV_TENANT,
    )

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
        category, _ = Category.objects.update_or_create(
            tenant=tenant,
            slug=category_data['slug'],
            defaults={'name': category_data['name']},
        )
        categories[category_data['slug']] = category

    for product_data in PRODUCTS:
        Product.objects.update_or_create(
            tenant=tenant,
            sku=product_data['sku'],
            defaults={
                'name': product_data['name'],
                'slug': product_data['slug'],
                'brand': brands[product_data['brand']],
                'category': categories[product_data['category']],
                'status': 'active',
                'base_price': product_data['base_price'],
                'tech_specs': product_data['tech_specs'],
            },
        )


def remove_sample_tech_products(apps, schema_editor):
    Tenant = apps.get_model('tenants', 'Tenant')
    Brand = apps.get_model('catalog', 'Brand')
    Category = apps.get_model('catalog', 'Category')
    Product = apps.get_model('catalog', 'Product')

    tenant = Tenant.objects.filter(slug=DEV_TENANT['slug']).first()
    if not tenant:
        return

    Product.objects.filter(
        tenant=tenant,
        sku__in=[product_data['sku'] for product_data in PRODUCTS],
    ).delete()
    Category.objects.filter(
        tenant=tenant,
        slug__in=[category_data['slug'] for category_data in CATEGORIES],
        products__isnull=True,
    ).delete()
    Brand.objects.filter(
        tenant=tenant,
        slug__in=[brand_data['slug'] for brand_data in BRANDS],
        products__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0005_alter_product_sku'),
    ]

    operations = [
        migrations.RunPython(seed_sample_tech_products, remove_sample_tech_products),
    ]
