from django.apps import AppConfig


class MesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.mes'
    verbose_name = 'Shop Floor Control (MES)'

    def ready(self):
        from . import signals  # noqa: F401
