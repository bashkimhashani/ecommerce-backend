from types import SimpleNamespace

from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from rest_framework_simplejwt.tokens import RefreshToken

from cart.models import Cart
from cart.services import CartService
from .serializers import (
    CustomTokenObtainPairSerializer,
    EmailVerificationSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
    UserProfileUpdateSerializer,
    UserSerializer,
)
from .tasks import send_email_verification_email, send_password_reset_email
from .token_blacklist import blacklist_token_in_redis
from .tokens import email_verification_token_generator


User = get_user_model()


class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as error:
            raise InvalidToken(error.args[0])

        self._merge_guest_cart(request, serializer.user)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

    @staticmethod
    def _merge_guest_cart(request, user):
        session = getattr(request, 'session', None)
        session_key = getattr(session, 'session_key', None)
        if not session_key:
            return

        guest_cart = Cart.objects.filter(
            session_key=session_key,
            status=Cart.Status.ACTIVE,
        ).first()
        if not guest_cart:
            return

        tenant = getattr(request, 'tenant', None) or user.tenant
        user_cart = CartService.get_or_create_cart(
            SimpleNamespace(user=user, tenant=tenant),
        )
        CartService.merge_carts(guest_cart, user_cart)


class CustomTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = email_verification_token_generator.make_token(user)
            send_email_verification_email.delay(user.id, uid, token)
            refresh = CustomTokenObtainPairSerializer.get_token(user)
            return Response({
                'user': UserSerializer(user).data,
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }, status=status.HTTP_201_CREATED)
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


class EmailVerificationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            if user.is_email_verified:
                return Response(
                    {'message': 'Email is already verified.'},
                    status=status.HTTP_200_OK,
                )
            user.is_email_verified = True
            user.save(update_fields=['is_email_verified'])
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

    def post(self, request):
        try:
            refresh_token = request.data['refresh']
            token = RefreshToken(refresh_token)
            blacklist_token_in_redis(token)
            if request.auth:
                blacklist_token_in_redis(request.auth)
            token.blacklist()
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

    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        if serializer.is_valid():
            email = User.objects.normalize_email(
                serializer.validated_data['email']
            )
            user = User.objects.filter(email=email, is_active=True).first()
            if user:
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                send_password_reset_email.delay(user.id, uid, token)
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

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            user.set_password(serializer.validated_data['new_password'])
            user.save(update_fields=['password'])
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

    def get(self, request):
        serializer = UserSerializer(
            request.user,
            context={'request': request},
        )
        return Response(serializer.data)

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
