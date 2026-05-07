from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User


ROLE_GROUPS = {
    'vendor_admin',
    'store_staff',
    'customer',
}


@receiver(post_save, sender=User)
def assign_role_group_on_create(sender, instance, created, **kwargs):
    if not created or instance.role not in ROLE_GROUPS:
        return

    group, _ = Group.objects.get_or_create(name=instance.role)
    instance.groups.add(group)
