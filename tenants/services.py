from users.serializers import CustomTokenObtainPairSerializer


class TenantRegistrationService:
    @staticmethod
    def build_registration_response(result):
        user = result['user']
        tenant = result['tenant']
        refresh = CustomTokenObtainPairSerializer.get_token(user)
        return {
            'tenant': tenant,
            'user': user,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }
