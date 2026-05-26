from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return (
            f"{user.pk}{user.password}{user.last_login}{timestamp}"
            f"{user.email}{user.is_email_verified}"
        )


email_verification_token_generator = EmailVerificationTokenGenerator()
