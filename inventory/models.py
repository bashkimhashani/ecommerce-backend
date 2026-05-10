from django.db import models
from catalog.models import Product
from vendor.models import VendorProfile
from tenants.models import Tenant

class Inventory(models.Model):
    """
    Inventory management for vendor products
    """
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='inventory')
    vendor = models.ForeignKey(VendorProfile, on_delete=models.CASCADE, related_name='inventory_items')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    
    quantity_available = models.IntegerField(default=0)
    reserved_quantity = models.IntegerField(default=0)  # Items in carts but not purchased
    low_stock_threshold = models.IntegerField(default=10)
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    cost_per_item = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_tracked = models.BooleanField(default=True)  # Track inventory or not
    
    # SKU and barcode
    sku = models.CharField(max_length=100, unique=True, blank=True)
    barcode = models.CharField(max_length=100, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['vendor', 'is_active']),
            models.Index(fields=['sku']),
            models.Index(fields=['tenant']),
        ]
    
    @property
    def available_quantity(self):
        return self.quantity_available - self.reserved_quantity
    
    def __str__(self):
        return f"{self.product.name} - {self.vendor.store_name}"
