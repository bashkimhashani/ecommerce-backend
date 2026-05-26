from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .history import ChatHistoryStore
from .serializers import (
    ChatHistoryResponseSerializer,
    ChatMessageSerializer,
    ChatResponseSerializer,
)
from .services import ChatWorkflowService
from .throttles import ChatRateThrottle


class ChatMessageView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ChatRateThrottle]
    history_store_class = ChatHistoryStore
    chat_workflow_service_class = ChatWorkflowService

    @extend_schema(
        tags=["AI Chat"],
        request=ChatMessageSerializer,
        responses={status.HTTP_200_OK: ChatResponseSerializer},
        examples=[
            OpenApiExample(
                "Chat message request",
                value={
                    "message": "Which laptop is best for programming?",
                    "session_id": "customer-session-123",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Chat message response",
                value={
                    "session_id": "customer-session-123",
                    "message": "The TechBook Pro is a strong match.",
                    "used_fallback": False,
                    "products": [
                        {
                            "name": "TechBook Pro 14",
                            "brand": "TechBrand",
                            "price": "1299.00",
                            "category": "Laptops",
                            "sku": "TB-PRO-14",
                            "tech_specs": {"ram": "16GB"},
                        },
                    ],
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = ChatMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        return Response(
            self.chat_workflow_service_class().respond(
                message=serializer.validated_data["message"],
                session_id=serializer.validated_data.get("session_id"),
                tenant=getattr(request, "tenant", None),
            ),
            status=status.HTTP_200_OK,
        )


class ChatHistoryView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    history_store_class = ChatHistoryStore

    @extend_schema(
        tags=["AI Chat"],
        responses={status.HTTP_200_OK: ChatHistoryResponseSerializer},
        examples=[
            OpenApiExample(
                "Chat history response",
                value={
                    "session_id": "customer-session-123",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Show me gaming laptops.",
                        },
                        {
                            "role": "assistant",
                            "content": "Here are a few catalog matches.",
                        },
                    ],
                },
                response_only=True,
            ),
        ],
    )
    def get(self, request, session_id):
        return Response(
            {
                "session_id": session_id,
                "messages": self.history_store_class().get_history(session_id),
            },
            status=status.HTTP_200_OK,
        )
