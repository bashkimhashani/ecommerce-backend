import json

import redis
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

CART_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60


class CartRedisCache:
    @staticmethod
    def key(session_key):
        return f"cart:{session_key}"

    @classmethod
    def store_cart(cls, cart):
        if not cart.session_key:
            return None

        payload = cls.serialize_cart(cart)
        client = cls.get_client()
        client.setex(
            cls.key(cart.session_key),
            CART_CACHE_TTL_SECONDS,
            json.dumps(payload, cls=DjangoJSONEncoder),
        )
        return payload

    @classmethod
    def get_cart(cls, session_key):
        if not session_key:
            return None

        cached_cart = cls.get_client().get(cls.key(session_key))
        if cached_cart is None:
            return None

        return json.loads(cached_cart)

    @classmethod
    def invalidate_cart(cls, session_key):
        if not session_key:
            return 0

        return cls.get_client().delete(cls.key(session_key))

    @staticmethod
    def serialize_cart(cart):
        items = []

        for item in cart.items.select_related("product_variant__product"):
            product_variant = item.product_variant
            product = getattr(product_variant, "product", None)
            variant_options = [
                getattr(product_variant, "color", ""),
                getattr(product_variant, "storage", ""),
                getattr(product_variant, "ram", ""),
            ]

            items.append(
                {
                    "id": item.id,
                    "product_variant_id": item.product_variant_id,
                    "product_name": getattr(product, "name", ""),
                    "variant_label": ", ".join(
                        option for option in variant_options if option
                    ),
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "line_total": item.line_total,
                }
            )

        return {
            "id": cart.id,
            "status": cart.status,
            "items": items,
            "total_items": cart.total_items,
            "subtotal": cart.subtotal,
            "created_at": cart.created_at,
            "updated_at": cart.updated_at,
        }

    @staticmethod
    def get_client():
        return redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
