from django.urls import path

from .views import CartDetailView, CartItemCreateView


urlpatterns = [
    path('', CartDetailView.as_view(), name='cart-detail'),
    path('items/', CartItemCreateView.as_view(), name='cart-item-list'),
]
