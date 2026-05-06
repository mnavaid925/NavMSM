from django.apps import AppConfig


class LaborConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.labor'
    verbose_name = 'Labor & Workforce Management'

    def ready(self):
        from . import signals  # noqa: F401
