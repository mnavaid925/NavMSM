from django.apps import AppConfig


class BiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.bi'
    verbose_name = 'Business Intelligence & Analytics'

    def ready(self):
        from . import signals  # noqa: F401
