from .models import RequestLog


class RequestLogService:
    @staticmethod
    def list_logs():
        return RequestLog.objects.all()
