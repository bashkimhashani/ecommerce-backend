from django.db import models
from django.contrib.auth import get_user_model
from tenants.models import Tenant

User = get_user_model()

class VendorProfile(models.Model):
    """   
    Modeli for vendor profile
    Supports multi-tenancy - each vendor belongs to a tenant
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='vendor_profile')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='vendors')
    store_name = models.CharField(max_length=255)
    store_description = models.TextField(blank=True, null=True)
    logo = models.URLField(blank=True, null=True)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    rating = models.FloatField(default=0.0)
    total_sales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'tenant']
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['store_name']),
        ]
    
    def __str__(self):
        return f"{self.store_name} - {self.tenant.name}"
