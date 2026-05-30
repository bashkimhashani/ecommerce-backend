from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .token_blacklist import is_token_blacklisted_in_redis


class RedisBlacklistJWTAuthentication(JWTAuthentication):
    def get_validated_token(self, raw_token):
        validated_token = super().get_validated_token(raw_token)
        if is_token_blacklisted_in_redis(validated_token):
            raise InvalidToken("Token is blacklisted.")
        return validated_token


class RedisBlacklistJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "users.authentication.RedisBlacklistJWTAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
