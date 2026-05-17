from django.apps import AppConfig


class WfaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.wfa'
    verbose_name = 'Workflow & Business Process Automation'

    def ready(self):
        from . import signals  # noqa: F401
