import uuid

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import ChatMessageSerializer
from .services import ChatService, ProductContextRetriever


class ChatMessageView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = ChatMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_message = serializer.validated_data['message']
        session_id = (
            serializer.validated_data.get('session_id')
            or uuid.uuid4().hex
        )
        tenant = getattr(request, 'tenant', None)
        history = self.get_history(session_id)
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

        self.save_history(
            session_id,
            [
                *history,
                {'role': 'user', 'content': user_message},
                {'role': 'assistant', 'content': assistant_message},
            ],
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

    def get_history(self, session_id):
        return cache.get(self.history_key(session_id), [])

    def save_history(self, session_id, history):
        cache.set(self.history_key(session_id), history[-20:], timeout=86400)

    def history_key(self, session_id):
        return f'chat:{session_id}:history'

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
