import logging
import time

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.perf_counter()
        response = self.get_response(request)
        response_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

        if request.path.startswith('/api/'):
            tenant_id = self.get_tenant_id(request)
            logger.info(
                (
                    'api_request method=%s path=%s status_code=%s '
                    'response_time_ms=%s tenant_id=%s'
                ),
                request.method,
                request.path,
                response.status_code,
                response_time_ms,
                tenant_id,
                extra={
                    'method': request.method,
                    'path': request.path,
                    'status_code': response.status_code,
                    'response_time_ms': response_time_ms,
                    'tenant_id': tenant_id,
                },
            )

        return response

    def get_tenant_id(self, request):
        tenant = getattr(request, 'tenant', None)
        tenant_id = getattr(tenant, 'id', None)

        if tenant_id is not None:
            return tenant_id

        return getattr(getattr(request, 'user', None), 'tenant_id', None)
