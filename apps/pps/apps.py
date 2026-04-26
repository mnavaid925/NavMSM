from django.apps import AppConfig


class PpsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.pps'
    verbose_name = 'Production Planning & Scheduling'

    def ready(self):
        from . import signals  # noqa: F401
