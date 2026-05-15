from django.apps import AppConfig


class DmsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.dms'
    verbose_name = 'Document & Knowledge Management'

    def ready(self):
        from . import signals  # noqa: F401
