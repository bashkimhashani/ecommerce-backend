from django.db import migrations


ROLE_GROUPS = [
    'vendor_admin',
    'store_staff',
    'customer',
]


def create_role_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for group_name in ROLE_GROUPS:
        Group.objects.get_or_create(name=group_name)


def delete_role_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=ROLE_GROUPS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_role_groups, delete_role_groups),
    ]
