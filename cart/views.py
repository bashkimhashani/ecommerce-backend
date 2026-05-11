from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import CartSerializer
from .services import CartService


class CartDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        cart = CartService.get_or_create_cart(request)
        serializer = CartSerializer(cart)
        return Response(serializer.data)
