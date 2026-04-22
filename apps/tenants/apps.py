from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.tenants'
    verbose_name = 'Tenant & Subscription Management'

    def ready(self):
        # Wire audit-log signals.
        from . import signals  # noqa: F401
