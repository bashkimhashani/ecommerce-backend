from datetime import datetime, timezone

from django_redis import get_redis_connection
from rest_framework_simplejwt.exceptions import TokenError

BLACKLIST_KEY_PREFIX = "auth:blacklisted"


def get_token_blacklist_key(jti):
    return f"{BLACKLIST_KEY_PREFIX}:{jti}"


def get_token_ttl(token):
    exp = token.get("exp")
    if not exp:
        raise TokenError("Token has no expiration claim.")

    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    return max(int((expires_at - now).total_seconds()), 0)


def blacklist_token_in_redis(token):
    ttl = get_token_ttl(token)
    jti = token.get("jti")
    if not jti:
        raise TokenError("Token has no JTI claim.")

    key = get_token_blacklist_key(jti)
    connection = get_redis_connection("default")
    connection.setex(key, ttl, "1")
    return key, ttl


def is_token_blacklisted_in_redis(token):
    jti = token.get("jti")
    if not jti:
        return False

    connection = get_redis_connection("default")
    return bool(connection.exists(get_token_blacklist_key(jti)))
