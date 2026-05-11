from django.urls import path

from .views import CartDetailView, CartItemCreateView, CartItemDetailView


urlpatterns = [
    path('', CartDetailView.as_view(), name='cart-detail'),
    path('items/', CartItemCreateView.as_view(), name='cart-item-list'),
    path(
        'items/<int:item_id>/',
        CartItemDetailView.as_view(),
        name='cart-item-detail',
    ),
]
