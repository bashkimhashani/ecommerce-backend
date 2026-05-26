import threading

_thread_locals = threading.local()


def get_current_tenant():
    return getattr(_thread_locals, "tenant", None)


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = None

        if request.user.is_authenticated:
            try:
                tenant = request.user.tenant
            except Exception:
                tenant = None

        request.tenant = tenant
        _thread_locals.tenant = tenant

        try:
            response = self.get_response(request)
        finally:
            if hasattr(_thread_locals, "tenant"):
                delattr(_thread_locals, "tenant")

        return response
