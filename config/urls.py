from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

from checkout.views import StripeWebhookView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('users.urls')),
    path('api/v1/catalog/', include('catalog.urls')),
    path('api/v1/users/', include('users.profile_urls')),
    path('api/v1/tenants/', include('tenants.urls')),
    path('api/v1/cart/', include('cart.urls')),
    path('api/v1/checkout/', include('checkout.urls')),
    path('api/v1/chat/', include('ai.urls')),
    path('api/v1/', include('orders.urls')),
    path('api/v1/admin/', include('request_logs.urls')),
    path(
        'api/v1/webhooks/stripe/',
        StripeWebhookView.as_view(),
        name='stripe-webhook',
    ),
    path('api/v1/vendor/', include('vendor.urls')),

    # Swagger
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(
        url_name='schema'), name='swagger-ui'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
