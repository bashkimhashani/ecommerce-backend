from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "users"

    def ready(self):
        import users.schema  # noqa: F401
        import users.signals  # noqa: F401
