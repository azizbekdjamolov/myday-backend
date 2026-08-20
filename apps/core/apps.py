from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        # Register model signals (audit log auto-population etc.).
        from . import signals  # noqa: F401