from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from users.serializers import CustomTokenObtainPairSerializer, UserSerializer

from .serializers import TenantRegistrationSerializer, TenantSerializer


class TenantRegisterView(APIView):
    permission_classes = [AllowAny]

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
