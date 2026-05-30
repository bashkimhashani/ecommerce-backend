from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from users.serializers import UserSerializer

from .serializers import TenantRegistrationSerializer, TenantSerializer
from .services import TenantRegistrationService


class TenantRegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Tenants"],
        request=TenantRegistrationSerializer,
        responses={
            status.HTTP_201_CREATED: OpenApiResponse(
                description="Tenant, owner user, and JWT pair.",
            ),
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description="Validation errors.",
            ),
        },
        examples=[
            OpenApiExample(
                "Tenant registration request",
                value={
                    "name": "Acme Store",
                    "slug": "acme-store",
                    "domain": "acme.example.com",
                    "plan": "basic",
                    "email": "owner@example.com",
                    "first_name": "Store",
                    "last_name": "Owner",
                    "password": "StrongPass123!",
                    "phone": "+38344123456",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Tenant registration response",
                value={
                    "tenant": {
                        "id": 1,
                        "name": "Acme Store",
                        "slug": "acme-store",
                        "domain": "acme.example.com",
                        "owner": 1,
                        "plan": "basic",
                        "is_active": True,
                    },
                    "user": {
                        "id": 1,
                        "email": "owner@example.com",
                        "role": "vendor_admin",
                    },
                    "access": "eyJhbGciOi...",
                    "refresh": "eyJhbGciOi...",
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = TenantRegistrationSerializer(
            data=request.data,
            context={"request": request},
        )
        if serializer.is_valid():
            result = TenantRegistrationService.register(serializer)
            return Response(
                {
                    "tenant": TenantSerializer(result["tenant"]).data,
                    "user": UserSerializer(result["user"]).data,
                    "access": result["access"],
                    "refresh": result["refresh"],
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )
