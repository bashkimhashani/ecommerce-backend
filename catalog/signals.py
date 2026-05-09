import logging
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django_redis import get_redis_connection
from PIL import Image

from .models import Product, ProductImage


logger = logging.getLogger(__name__)

IMAGE_SIZES = {
    'thumbnail': (150, 150),
    'medium': (600, 600),
    'large': (1200, 1200),
}


def delete_cache_pattern(pattern):
    try:
        connection = get_redis_connection('default')
        keys = list(connection.scan_iter(match=pattern))
        if keys:
            connection.delete(*keys)
    except Exception:
        logger.exception(
            'Failed to invalidate catalog cache pattern: %s',
            pattern,
        )


def invalidate_product_cache(product):
    tenant_scope = (
        f'tenant:{product.tenant_id}'
        if product.tenant_id
        else 'tenant:public'
    )
    patterns = [
        f'*catalog:product-list:{tenant_scope}:*',
        '*catalog:product-list:tenant:public:*',
        f'*catalog:product-detail:{tenant_scope}:{product.slug}',
        f'*catalog:product-detail:tenant:public:{product.slug}',
    ]

    for pattern in patterns:
        delete_cache_pattern(pattern)


@receiver(post_save, sender=Product)
def invalidate_product_cache_after_save(sender, instance, **kwargs):
    invalidate_product_cache(instance)


@receiver(post_delete, sender=Product)
def invalidate_product_cache_after_delete(sender, instance, **kwargs):
    invalidate_product_cache(instance)


def build_generated_image_path(original_name, product_image_id, size_name):
    original_path = Path(original_name)
    return f'{product_image_id}/{original_path.stem}_{size_name}.jpg'


def render_resized_image(source_image, max_size):
    image = source_image.copy()
    image.thumbnail(max_size, Image.Resampling.LANCZOS)

    if image.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.getchannel('A'))
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')

    output = BytesIO()
    image.save(output, format='JPEG', quality=85, optimize=True)
    output.seek(0)
    return ContentFile(output.read())


@receiver(post_save, sender=ProductImage)
def generate_product_image_sizes(sender, instance, created, update_fields=None, **kwargs):
    if not instance.image:
        return
    if not created and update_fields is not None and 'image' not in update_fields:
        return

    try:
        instance.image.open('rb')
        source_image = Image.open(instance.image)
        source_image.load()
    except (FileNotFoundError, OSError, ValueError):
        return
    finally:
        instance.image.close()

    for field_name, max_size in IMAGE_SIZES.items():
        generated_file = render_resized_image(source_image, max_size)
        generated_path = build_generated_image_path(
            instance.image.name,
            instance.id,
            field_name,
        )
        getattr(instance, field_name).save(
            generated_path,
            generated_file,
            save=False,
        )

    ProductImage.all_objects.filter(pk=instance.pk).update(
        thumbnail=instance.thumbnail.name,
        medium=instance.medium.name,
        large=instance.large.name,
    )
