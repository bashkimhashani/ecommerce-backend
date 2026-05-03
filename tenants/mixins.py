from django.db import models
from .middleware import get_current_tenant


class TenantAwareManager(models.Manager):
    def get_queryset(self):
        tenant = get_current_tenant()
        qs = super().get_queryset()
        if tenant:
            return qs.filter(tenant=tenant)
        return qs


class TenantModel(models.Model):
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='%(class)s_set'
    )

    objects = TenantAwareManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True