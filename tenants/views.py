from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from users.serializers import CustomTokenObtainPairSerializer, UserSerializer

from .serializers import TenantRegistrationSerializer, TenantSerializer


class TenantRegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Tenants'],
        request=TenantRegistrationSerializer,
        responses={
            status.HTTP_201_CREATED: OpenApiResponse(
                description='Tenant, owner user, and JWT pair.',
            ),
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description='Validation errors.',
            ),
        },
        examples=[
            OpenApiExample(
                'Tenant registration request',
                value={
                    'name': 'Acme Store',
                    'slug': 'acme-store',
                    'domain': 'acme.example.com',
                    'plan': 'basic',
                    'email': 'owner@example.com',
                    'first_name': 'Store',
                    'last_name': 'Owner',
                    'password': 'StrongPass123!',
                    'phone': '+38344123456',
                },
                request_only=True,
            ),
            OpenApiExample(
                'Tenant registration response',
                value={
                    'tenant': {
                        'id': 1,
                        'name': 'Acme Store',
                        'slug': 'acme-store',
                        'domain': 'acme.example.com',
                        'owner': 1,
                        'plan': 'basic',
                        'is_active': True,
                    },
                    'user': {
                        'id': 1,
                        'email': 'owner@example.com',
                        'role': 'vendor_admin',
                    },
                    'access': 'eyJhbGciOi...',
                    'refresh': 'eyJhbGciOi...',
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = TenantRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            user = result['user']
            tenant = result['tenant']
            refresh = CustomTokenObtainPairSerializer.get_token(user)
            return Response({
                'tenant': TenantSerializer(tenant).data,
                'user': UserSerializer(user).data,
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }, status=status.HTTP_201_CREATED)
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )
