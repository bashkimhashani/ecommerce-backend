from types import SimpleNamespace
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from .middleware import RequestLoggingMiddleware


class RequestLoggingMiddlewareTests(SimpleTestCase):
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

    @patch('config.middleware.logger.info')
    def test_skips_non_api_requests(self, logger_info):
        middleware = RequestLoggingMiddleware(
            lambda request: HttpResponse(status=200),
        )
        request = self.factory.get('/admin/')

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        logger_info.assert_not_called()

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
        self.assertEqual(perf_counter.call_count, 2)
