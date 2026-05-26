import logging
import time

logger = logging.getLogger("request_logs")


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.perf_counter()
        response = self.get_response(request)
        response_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

        if request.path.startswith("/api/"):
            self.log_request(request, response, response_time_ms)

        return response

    def log_request(self, request, response, response_time_ms):
        tenant_id = self.get_tenant_id(request)
        log_data = {
            "method": request.method,
            "path": request.path,
            "status_code": response.status_code,
            "response_time_ms": response_time_ms,
            "tenant_id": tenant_id,
        }

        logger.info(
            (
                "api_request method=%s path=%s status_code=%s "
                "response_time_ms=%s tenant_id=%s"
            ),
            log_data["method"],
            log_data["path"],
            log_data["status_code"],
            log_data["response_time_ms"],
            log_data["tenant_id"],
            extra=log_data,
        )
        self.create_request_log(log_data)

    def create_request_log(self, log_data):
        try:
            from request_logs.models import RequestLog

            RequestLog.objects.create(**log_data)
        except Exception:
            logger.exception("failed_to_persist_request_log")

    def get_tenant_id(self, request):
        tenant = getattr(request, "tenant", None)
        tenant_id = getattr(tenant, "id", None)

        if tenant_id is not None:
            return tenant_id

        return getattr(getattr(request, "user", None), "tenant_id", None)
