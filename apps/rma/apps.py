from django.apps import AppConfig


class RmaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.rma'
    verbose_name = 'Returns & RMA Management'

    def ready(self):
        from . import signals  # noqa: F401
