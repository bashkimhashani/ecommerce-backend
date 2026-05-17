import django_fsm
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='status',
            field=django_fsm.FSMField(
                choices=[
                    ('pending', 'Pending'),
                    ('confirmed', 'Confirmed'),
                    ('processing', 'Processing'),
                    ('shipped', 'Shipped'),
                    ('delivered', 'Delivered'),
                    ('cancelled', 'Cancelled'),
                ],
                db_index=True,
                default='pending',
                max_length=20,
                protected=True,
            ),
        ),
    ]
