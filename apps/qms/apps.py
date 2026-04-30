from django.apps import AppConfig


class QmsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.qms'
    verbose_name = 'Quality Management (QMS)'

    def ready(self):
        from . import signals  # noqa: F401
