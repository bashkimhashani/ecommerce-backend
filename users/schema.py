from drf_spectacular.extensions import OpenApiAuthenticationExtension


class RedisBlacklistJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "users.authentication.RedisBlacklistJWTAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT access token using the Bearer authentication scheme.",
        }
