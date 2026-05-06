from django.apps import AppConfig


class CostConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.cost'
    verbose_name = 'Cost Management & Accounting'

    def ready(self):
        from . import signals  # noqa: F401
