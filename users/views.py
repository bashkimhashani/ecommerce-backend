from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .serializers import (
    CustomTokenObtainPairSerializer,
    EmailVerificationSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
    UserProfileUpdateSerializer,
    UserSerializer,
)
from .services import AuthService


class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = CustomTokenObtainPairSerializer

    @extend_schema(
        tags=['Auth'],
        request=CustomTokenObtainPairSerializer,
        responses={
            status.HTTP_200_OK: inline_serializer(
                name='TokenPairResponse',
                fields={
                    'access': serializers.CharField(),
                    'refresh': serializers.CharField(),
                },
            ),
        },
        examples=[
            OpenApiExample(
                'Login request',
                value={
                    'email': 'customer@example.com',
                    'password': 'DemoPass123!',
                },
                request_only=True,
            ),
            OpenApiExample(
                'Login response',
                value={
                    'access': 'eyJhbGciOi...',
                    'refresh': 'eyJhbGciOi...',
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as error:
            raise InvalidToken(error.args[0])

        AuthService.merge_guest_cart(request, serializer.user)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class CustomTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Auth'],
        request=inline_serializer(
            name='TokenRefreshRequest',
            fields={'refresh': serializers.CharField()},
        ),
        responses={
            status.HTTP_200_OK: inline_serializer(
                name='TokenRefreshResponse',
                fields={'access': serializers.CharField()},
            ),
        },
        examples=[
            OpenApiExample(
                'Token refresh request',
                value={'refresh': 'eyJhbGciOi...'},
                request_only=True,
            ),
            OpenApiExample(
                'Token refresh response',
                value={'access': 'eyJhbGciOi...'},
                response_only=True,
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Auth'],
        request=RegisterSerializer,
        responses={
            status.HTTP_201_CREATED: inline_serializer(
                name='RegisterResponse',
                fields={
                    'user': UserSerializer(),
                    'access': serializers.CharField(),
                    'refresh': serializers.CharField(),
                },
            ),
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description='Validation errors.',
            ),
        },
        examples=[
            OpenApiExample(
                'Register request',
                value={
                    'email': 'customer@example.com',
                    'first_name': 'Customer',
                    'last_name': 'User',
                    'password': 'StrongPass123!',
                    'role': 'customer',
                },
                request_only=True,
            ),
            OpenApiExample(
                'Register response',
                value={
                    'user': {
                        'id': 1,
                        'email': 'customer@example.com',
                        'first_name': 'Customer',
                        'last_name': 'User',
                        'role': 'customer',
                        'is_email_verified': False,
                    },
                    'access': 'eyJhbGciOi...',
                    'refresh': 'eyJhbGciOi...',
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token_pair = AuthService.complete_registration(user)
            return Response({
                'user': UserSerializer(user).data,
                **token_pair,
            }, status=status.HTTP_201_CREATED)
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


class EmailVerificationView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Auth'],
        request=EmailVerificationSerializer,
        responses={
            status.HTTP_200_OK: inline_serializer(
                name='EmailVerificationResponse',
                fields={'message': serializers.CharField()},
            ),
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description='Invalid or expired verification token.',
            ),
        },
        examples=[
            OpenApiExample(
                'Email verification request',
                value={'uid': 'MQ', 'token': 'email-verification-token'},
                request_only=True,
            ),
            OpenApiExample(
                'Email verification response',
                value={'message': 'Email has been verified successfully.'},
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            if not AuthService.verify_email(user):
                return Response(
                    {'message': 'Email is already verified.'},
                    status=status.HTTP_200_OK,
                )
            return Response(
                {'message': 'Email has been verified successfully.'},
                status=status.HTTP_200_OK,
            )
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Auth'],
        request=inline_serializer(
            name='LogoutRequest',
            fields={'refresh': serializers.CharField()},
        ),
        responses={
            status.HTTP_200_OK: inline_serializer(
                name='LogoutResponse',
                fields={'message': serializers.CharField()},
            ),
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description='Invalid token.',
            ),
        },
        examples=[
            OpenApiExample(
                'Logout request',
                value={'refresh': 'eyJhbGciOi...'},
                request_only=True,
            ),
            OpenApiExample(
                'Logout response',
                value={'message': 'Logged out successfully'},
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        try:
            AuthService.logout(
                refresh_token=request.data['refresh'],
                access_token=request.auth,
            )
            return Response(
                {'message': 'Logged out successfully'},
                status=status.HTTP_200_OK
            )
        except Exception:
            return Response(
                {'error': 'Invalid token'},
                status=status.HTTP_400_BAD_REQUEST
            )


class PasswordResetView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Auth'],
        request=PasswordResetSerializer,
        responses={
            status.HTTP_200_OK: inline_serializer(
                name='PasswordResetResponse',
                fields={'message': serializers.CharField()},
            ),
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description='Invalid password reset request.',
            ),
        },
        examples=[
            OpenApiExample(
                'Password reset request',
                value={'email': 'customer@example.com'},
                request_only=True,
            ),
            OpenApiExample(
                'Password reset response',
                value={
                    'message': (
                        'If an account exists for this email, a password '
                        'reset link has been sent.'
                    ),
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        if serializer.is_valid():
            AuthService.request_password_reset(
                serializer.validated_data['email'],
            )
            return Response(
                {
                    'message': (
                        'If an account exists for this email, a password '
                        'reset link has been sent.'
                    )
                },
                status=status.HTTP_200_OK,
            )
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Auth'],
        request=PasswordResetConfirmSerializer,
        responses={
            status.HTTP_200_OK: inline_serializer(
                name='PasswordResetConfirmResponse',
                fields={'message': serializers.CharField()},
            ),
            status.HTTP_400_BAD_REQUEST: OpenApiResponse(
                description='Invalid or expired reset token.',
            ),
        },
        examples=[
            OpenApiExample(
                'Password reset confirm request',
                value={
                    'uid': 'MQ',
                    'token': 'password-reset-token',
                    'new_password': 'NewStrongPass123!',
                },
                request_only=True,
            ),
            OpenApiExample(
                'Password reset confirm response',
                value={'message': 'Password has been reset successfully.'},
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            AuthService.reset_password(
                serializer.validated_data['user'],
                serializer.validated_data['new_password'],
            )
            return Response(
                {'message': 'Password has been reset successfully.'},
                status=status.HTTP_200_OK,
            )
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @extend_schema(
        tags=['Users'],
        responses={status.HTTP_200_OK: UserSerializer},
        examples=[
            OpenApiExample(
                'Current user response',
                value={
                    'id': 1,
                    'email': 'customer@example.com',
                    'first_name': 'Customer',
                    'last_name': 'User',
                    'role': 'customer',
                    'tenant': 1,
                    'phone': '+38344123456',
                    'is_email_verified': True,
                    'avatar': None,
                    'avatar_thumbnail': None,
                },
                response_only=True,
            ),
        ],
    )
    def get(self, request):
        serializer = UserSerializer(
            request.user,
            context={'request': request},
        )
        return Response(serializer.data)

    @extend_schema(
        tags=['Users'],
        request=UserProfileUpdateSerializer,
        responses={status.HTTP_200_OK: UserSerializer},
        examples=[
            OpenApiExample(
                'Profile update request',
                value={
                    'first_name': 'Customer',
                    'last_name': 'Updated',
                    'phone': '+38344123456',
                },
                request_only=True,
            ),
            OpenApiExample(
                'Profile update response',
                value={
                    'id': 1,
                    'email': 'customer@example.com',
                    'first_name': 'Customer',
                    'last_name': 'Updated',
                    'role': 'customer',
                    'tenant': 1,
                    'phone': '+38344123456',
                    'is_email_verified': True,
                },
                response_only=True,
            ),
        ],
    )
    def patch(self, request):
        serializer = UserProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )
