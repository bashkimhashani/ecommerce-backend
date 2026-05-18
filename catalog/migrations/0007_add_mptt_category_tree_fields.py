import django.db.models.deletion
import mptt.fields
from django.db import migrations, models


def initialize_category_tree_fields(apps, schema_editor):
    Category = apps.get_model('catalog', 'Category')

    for tree_id, category in enumerate(
        Category.objects.order_by('tenant_id', 'name', 'id'),
        start=1,
    ):
        category.parent_id = None
        category.level = 0
        category.lft = 1
        category.rght = 2
        category.tree_id = tree_id
        category.save(
            update_fields=[
                'parent',
                'level',
                'lft',
                'rght',
                'tree_id',
            ],
        )


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0006_seed_sample_tech_products'),
    ]

    operations = [
        migrations.AddField(
            model_name='category',
            name='parent',
            field=mptt.fields.TreeForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='children',
                to='catalog.category',
            ),
        ),
        migrations.AddField(
            model_name='category',
            name='icon_url',
            field=models.URLField(blank=True, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='category',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='category',
            name='level',
            field=models.PositiveIntegerField(default=0, editable=False),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='category',
            name='lft',
            field=models.PositiveIntegerField(default=0, editable=False),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='category',
            name='rght',
            field=models.PositiveIntegerField(default=0, editable=False),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='category',
            name='tree_id',
            field=models.PositiveIntegerField(db_index=True, default=0, editable=False),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name='category',
            options={
                'ordering': ['tree_id', 'lft'],
                'verbose_name_plural': 'categories',
            },
        ),
        migrations.RunPython(
            initialize_category_tree_fields,
            migrations.RunPython.noop,
        ),
    ]
