from django.apps import AppConfig


class SalesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.sales'
    verbose_name = 'Sales & Customer Order Management'

    def ready(self):
        from . import signals  # noqa: F401
