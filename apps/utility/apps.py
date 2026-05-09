from django.apps import AppConfig


class UtilityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.utility'
    verbose_name = 'Energy & Utility Management'

    def ready(self):
        from . import signals  # noqa: F401
