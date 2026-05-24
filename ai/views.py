import uuid

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .history import ChatHistoryStore
from .serializers import ChatMessageSerializer
from .services import ChatService, ProductContextRetriever
from .throttles import ChatRateThrottle


class ChatMessageView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ChatRateThrottle]
    history_store_class = ChatHistoryStore

    def post(self, request):
        serializer = ChatMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_message = serializer.validated_data['message']
        session_id = (
            serializer.validated_data.get('session_id')
            or uuid.uuid4().hex
        )
        tenant = getattr(request, 'tenant', None)
        history_store = self.history_store_class()
        history = history_store.get_history(session_id)
        products = ProductContextRetriever().get_relevant_products(
            user_message,
            tenant=tenant,
        )
        system_prompt = self.build_system_prompt(products)
        messages = [
            *history,
            {'role': 'user', 'content': user_message},
        ][-20:]
        used_fallback = False

        try:
            assistant_message = ChatService().complete(
                messages=messages,
                system_prompt=system_prompt,
            )
        except Exception:
            used_fallback = True
            assistant_message = self.build_fallback_answer(products)

        history_store.append_turn(
            session_id=session_id,
            tenant=tenant,
            user_message=user_message,
            assistant_message=assistant_message,
        )
        return Response(
            {
                'session_id': session_id,
                'message': assistant_message,
                'used_fallback': used_fallback,
                'products': products,
            },
            status=status.HTTP_200_OK,
        )

    def build_system_prompt(self, products):
        return (
            f'{settings.OPENAI_CHAT_SYSTEM_PROMPT}\n\n'
            f'Catalog context:\n{self.format_products(products)}'
        )

    def format_products(self, products):
        if not products:
            return 'No matching catalog products were found for this question.'
        return '\n'.join(
            (
                f"- {product['name']} ({product['brand']}): "
                f"${product['price']}; category {product['category']}; "
                f"SKU {product['sku']}; specs {product['tech_specs']}"
            )
            for product in products
        )

    def build_fallback_answer(self, products):
        if not products:
            return (
                'I can help with tech products, prices, specs, cart, checkout, '
                'and account questions. I could not find a matching catalog '
                'item for that message, so try asking for a product type like '
                'laptop, phone, keyboard, or monitor.'
            )

        product_lines = [
            f"{product['name']} by {product['brand']} at ${product['price']}"
            for product in products[:3]
        ]
        return (
            'Here are a few catalog matches I can recommend: '
            f"{'; '.join(product_lines)}. "
            'Tell me your budget or preferred specs and I can narrow it down.'
        )


class ChatHistoryView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    history_store_class = ChatHistoryStore

    def get(self, request, session_id):
        return Response(
            {
                'session_id': session_id,
                'messages': self.history_store_class().get_history(session_id),
            },
            status=status.HTTP_200_OK,
        )
