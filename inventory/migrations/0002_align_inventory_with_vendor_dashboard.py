import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def migrate_inventory_variants(apps, schema_editor):
    Inventory = apps.get_model('inventory', 'Inventory')
    ProductVariant = apps.get_model('catalog', 'ProductVariant')

    for inventory in Inventory.objects.select_related('product').all():
        product = inventory.product
        variant = ProductVariant.objects.filter(
            product=product,
            tenant=inventory.tenant,
        ).first()

        if variant is None:
            variant = ProductVariant.objects.create(
                product=product,
                tenant=inventory.tenant,
                variant_price=product.base_price,
                stock_quantity=getattr(inventory, 'quantity_available', 0),
            )

        inventory.product_variant = variant
        inventory.quantity = getattr(inventory, 'quantity_available', 0)
        inventory.last_updated = getattr(inventory, 'updated_at', timezone.now())
        inventory.save(update_fields=['product_variant', 'quantity', 'last_updated'])


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0009_product_description'),
        ('inventory', '0001_initial'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='inventory',
            name='inventory_i_vendor__ce8a7f_idx',
        ),
        migrations.RemoveIndex(
            model_name='inventory',
            name='inventory_i_sku_78cea7_idx',
        ),
        migrations.RemoveIndex(
            model_name='inventory',
            name='inventory_i_tenant__de3241_idx',
        ),
        migrations.AddField(
            model_name='inventory',
            name='product_variant',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='inventory_items',
                to='catalog.productvariant',
            ),
        ),
        migrations.AddField(
            model_name='inventory',
            name='quantity',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='inventory',
            name='last_updated',
            field=models.DateTimeField(auto_now=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='inventory',
            name='tenant',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='%(class)s_set',
                to='tenants.tenant',
            ),
        ),
        migrations.RunPython(
            migrate_inventory_variants,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name='inventory',
            name='barcode',
        ),
        migrations.RemoveField(
            model_name='inventory',
            name='compare_at_price',
        ),
        migrations.RemoveField(
            model_name='inventory',
            name='cost_per_item',
        ),
        migrations.RemoveField(
            model_name='inventory',
            name='is_active',
        ),
        migrations.RemoveField(
            model_name='inventory',
            name='is_tracked',
        ),
        migrations.RemoveField(
            model_name='inventory',
            name='price',
        ),
        migrations.RemoveField(
            model_name='inventory',
            name='product',
        ),
        migrations.RemoveField(
            model_name='inventory',
            name='quantity_available',
        ),
        migrations.RemoveField(
            model_name='inventory',
            name='reserved_quantity',
        ),
        migrations.RemoveField(
            model_name='inventory',
            name='sku',
        ),
        migrations.RemoveField(
            model_name='inventory',
            name='updated_at',
        ),
        migrations.AlterField(
            model_name='inventory',
            name='low_stock_threshold',
            field=models.PositiveIntegerField(default=10),
        ),
        migrations.AlterField(
            model_name='inventory',
            name='product_variant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='inventory_items',
                to='catalog.productvariant',
            ),
        ),
        migrations.AddIndex(
            model_name='inventory',
            index=models.Index(fields=['vendor'], name='inventory_i_vendor__844827_idx'),
        ),
        migrations.AddIndex(
            model_name='inventory',
            index=models.Index(fields=['tenant'], name='inventory_i_tenant__de3241_idx'),
        ),
        migrations.AddIndex(
            model_name='inventory',
            index=models.Index(fields=['product_variant'], name='inventory_i_product_319f09_idx'),
        ),
        migrations.AddConstraint(
            model_name='inventory',
            constraint=models.UniqueConstraint(
                fields=('tenant', 'product_variant'),
                name='unique_inventory_variant_per_tenant',
            ),
        ),
    ]
