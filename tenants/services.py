from users.serializers import CustomTokenObtainPairSerializer


class TenantRegistrationService:
    @classmethod
    def register(cls, serializer):
        return cls.build_registration_response(serializer.save())

    @staticmethod
    def build_registration_response(result):
        user = result["user"]
        tenant = result["tenant"]
        refresh = CustomTokenObtainPairSerializer.get_token(user)
        return {
            "tenant": tenant,
            "user": user,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
