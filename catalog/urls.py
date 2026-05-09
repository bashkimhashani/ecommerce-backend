from django.urls import path

from .views import (
    CategoryTreeView,
    ProductImageDeleteView,
    ProductImageUploadView,
)


urlpatterns = [
    path(
        'categories/tree/',
        CategoryTreeView.as_view(),
        name='category-tree',
    ),
    path(
        'products/<slug:slug>/images/',
        ProductImageUploadView.as_view(),
        name='product-image-upload',
    ),
    path(
        'products/<slug:slug>/images/<int:image_id>/',
        ProductImageDeleteView.as_view(),
        name='product-image-delete',
    ),
]
