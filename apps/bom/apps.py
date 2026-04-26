from django.apps import AppConfig


class BomConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.bom'
    verbose_name = 'Bill of Materials Management'

    def ready(self):
        # Wire audit-log signals.
        from . import signals  # noqa: F401
