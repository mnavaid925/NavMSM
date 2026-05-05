from django.apps import AppConfig


class EamConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.eam'
    verbose_name = 'Equipment & Asset Management'

    def ready(self):
        from . import signals  # noqa: F401
