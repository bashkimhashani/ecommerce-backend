from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Category
from .serializers import CategoryTreeSerializer


class CategoryTreeView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=CategoryTreeSerializer(many=True),
        tags=['Catalog'],
    )
    def get(self, request):
        categories = Category.all_objects.filter(
            parent__isnull=True,
            is_active=True,
        )

        if request.user.is_authenticated and request.user.tenant_id:
            categories = categories.filter(tenant=request.user.tenant)

        categories = categories.order_by('tree_id', 'lft')
        serializer = CategoryTreeSerializer(categories, many=True)
        return Response(serializer.data)
