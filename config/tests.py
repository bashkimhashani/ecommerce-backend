from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from request_logs.models import RequestLog

from .middleware import RequestLoggingMiddleware


class RequestLoggingMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch('config.middleware.time.perf_counter', side_effect=[10.0, 10.12345])
    @patch('config.middleware.logger.info')
    def test_logs_api_request_metadata(self, logger_info, perf_counter):
        middleware = RequestLoggingMiddleware(
            lambda request: HttpResponse(status=201),
        )
        request = self.factory.post('/api/v1/cart/')
        request.tenant = SimpleNamespace(id=42)

        response = middleware(request)

        self.assertEqual(response.status_code, 201)
        logger_info.assert_called_once()

        message, method, path, status_code, response_time_ms, tenant_id = (
            logger_info.call_args.args
        )
        self.assertIn('api_request', message)
        self.assertEqual(method, 'POST')
        self.assertEqual(path, '/api/v1/cart/')
        self.assertEqual(status_code, 201)
        self.assertEqual(response_time_ms, 123.45)
        self.assertEqual(tenant_id, 42)
        self.assertEqual(
            logger_info.call_args.kwargs['extra'],
            {
                'method': 'POST',
                'path': '/api/v1/cart/',
                'status_code': 201,
                'response_time_ms': 123.45,
                'tenant_id': 42,
            },
        )
        self.assertEqual(perf_counter.call_count, 2)

        request_log = RequestLog.objects.get()
        self.assertEqual(request_log.method, 'POST')
        self.assertEqual(request_log.path, '/api/v1/cart/')
        self.assertEqual(request_log.status_code, 201)
        self.assertEqual(request_log.response_time_ms, Decimal('123.45'))
        self.assertEqual(request_log.tenant_id, 42)

    @patch('config.middleware.logger.info')
    def test_skips_non_api_requests(self, logger_info):
        middleware = RequestLoggingMiddleware(
            lambda request: HttpResponse(status=200),
        )
        request = self.factory.get('/admin/')

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        logger_info.assert_not_called()
        self.assertEqual(RequestLog.objects.count(), 0)

    @patch('config.middleware.time.perf_counter', side_effect=[1.0, 1.01])
    @patch('config.middleware.logger.info')
    def test_falls_back_to_user_tenant_id(self, logger_info, perf_counter):
        middleware = RequestLoggingMiddleware(
            lambda request: HttpResponse(status=204),
        )
        request = self.factory.delete('/api/v1/catalog/products/1/')
        request.user = SimpleNamespace(tenant_id=99)

        middleware(request)

        self.assertEqual(
            logger_info.call_args.kwargs['extra']['tenant_id'],
            99,
        )
        self.assertEqual(RequestLog.objects.get().tenant_id, 99)
        self.assertEqual(perf_counter.call_count, 2)

    @patch('config.middleware.time.perf_counter', side_effect=[2.0, 2.025])
    @patch('config.middleware.logger.info')
    def test_logs_authenticated_api_request(self, logger_info, perf_counter):
        middleware = RequestLoggingMiddleware(
            lambda request: HttpResponse(status=200),
        )
        request = self.factory.get('/api/v1/orders/')
        request.user = SimpleNamespace(
            is_authenticated=True,
            tenant_id=123,
        )

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        logger_info.assert_called_once()
        self.assertEqual(
            logger_info.call_args.kwargs['extra'],
            {
                'method': 'GET',
                'path': '/api/v1/orders/',
                'status_code': 200,
                'response_time_ms': 25.0,
                'tenant_id': 123,
            },
        )
        request_log = RequestLog.objects.get()
        self.assertEqual(request_log.method, 'GET')
        self.assertEqual(request_log.path, '/api/v1/orders/')
        self.assertEqual(request_log.status_code, 200)
        self.assertEqual(request_log.response_time_ms, Decimal('25.00'))
        self.assertEqual(request_log.tenant_id, 123)
        self.assertEqual(perf_counter.call_count, 2)

    @patch('config.middleware.time.perf_counter', side_effect=[3.0, 3.004])
    @patch('config.middleware.logger.info')
    def test_logs_unauthenticated_api_request(self, logger_info, perf_counter):
        middleware = RequestLoggingMiddleware(
            lambda request: HttpResponse(status=401),
        )
        request = self.factory.get('/api/v1/orders/')

        response = middleware(request)

        self.assertEqual(response.status_code, 401)
        logger_info.assert_called_once()
        self.assertEqual(
            logger_info.call_args.kwargs['extra'],
            {
                'method': 'GET',
                'path': '/api/v1/orders/',
                'status_code': 401,
                'response_time_ms': 4.0,
                'tenant_id': None,
            },
        )
        request_log = RequestLog.objects.get()
        self.assertEqual(request_log.method, 'GET')
        self.assertEqual(request_log.path, '/api/v1/orders/')
        self.assertEqual(request_log.status_code, 401)
        self.assertEqual(request_log.response_time_ms, Decimal('4.00'))
        self.assertIsNone(request_log.tenant_id)
        self.assertEqual(perf_counter.call_count, 2)
