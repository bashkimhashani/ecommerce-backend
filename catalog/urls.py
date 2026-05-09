from django.urls import path

from .views import (
    CategoryTreeView,
    ProductDetailView,
    ProductImageDeleteView,
    ProductImageUploadView,
    ProductListView,
    ProductSearchView,
)


urlpatterns = [
    path(
        'categories/tree/',
        CategoryTreeView.as_view(),
        name='category-tree',
    ),
    path(
        'products/',
        ProductListView.as_view(),
        name='product-list',
    ),
    path(
        'products/search/',
        ProductSearchView.as_view(),
        name='product-search',
    ),
    path(
        'products/<slug:slug>/',
        ProductDetailView.as_view(),
        name='product-detail',
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
