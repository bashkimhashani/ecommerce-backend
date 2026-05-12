import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_order_status_fsm'),
        ('tenants', '0002_tenant_owner'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderEvent',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('from_status', models.CharField(blank=True, max_length=20)),
                ('to_status', models.CharField(max_length=20)),
                ('transition', models.CharField(max_length=100)),
                ('note', models.TextField(blank=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'order',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='events',
                        to='orders.order',
                    ),
                ),
                (
                    'tenant',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='%(class)s_set',
                        to='tenants.tenant',
                    ),
                ),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='orderevent',
            index=models.Index(
                fields=['tenant', 'order'],
                name='orders_orde_tenant__ffc56c_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='orderevent',
            index=models.Index(
                fields=['tenant', 'to_status'],
                name='orders_orde_tenant__5c4b3d_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='orderevent',
            index=models.Index(
                fields=['created_at'],
                name='orders_orde_created_e6ae50_idx',
            ),
        ),
    ]
