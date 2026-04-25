from django.apps import AppConfig


class PlmConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.plm'
    verbose_name = 'Product Lifecycle Management'

    def ready(self):
        # Wire audit-log signals.
        from . import signals  # noqa: F401
