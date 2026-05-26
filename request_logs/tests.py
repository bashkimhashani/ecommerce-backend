from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User

from .models import RequestLog


class AdminRequestLogListViewTests(APITestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            email="superadmin@example.com",
            password="StrongPass123",
            first_name="Super",
            last_name="Admin",
        )
        self.customer = User.objects.create_user(
            email="customer@example.com",
            password="StrongPass123",
            first_name="Customer",
            last_name="User",
            role="customer",
        )

    def test_superadmin_can_list_paginated_request_logs(self):
        RequestLog.objects.create(
            method="GET",
            path="/api/v1/cart/",
            status_code=200,
            response_time_ms=Decimal("12.50"),
            tenant_id=1,
        )
        RequestLog.objects.create(
            method="POST",
            path="/api/v1/checkout/session/",
            status_code=201,
            response_time_ms=Decimal("24.25"),
            tenant_id=1,
        )
        RequestLog.objects.create(
            method="GET",
            path="/api/v1/orders/",
            status_code=200,
            response_time_ms=Decimal("8.75"),
            tenant_id=2,
        )
        self.client.force_authenticate(user=self.superadmin)

        response = self.client.get(
            reverse("admin-request-log-list"),
            {"page_size": 2},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertIsNotNone(response.data["next"])
        self.assertIsNone(response.data["previous"])
        self.assertEqual(
            set(response.data["results"][0].keys()),
            {
                "id",
                "method",
                "path",
                "status_code",
                "response_time_ms",
                "tenant_id",
                "created_at",
            },
        )

    def test_request_logs_require_superadmin_role(self):
        RequestLog.objects.create(
            method="GET",
            path="/api/v1/cart/",
            status_code=200,
            response_time_ms=Decimal("12.50"),
        )
        self.client.force_authenticate(user=self.customer)

        response = self.client.get(reverse("admin-request-log-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
