"""Audit-log signal wiring for sensitive models."""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from apps.core.models import get_current_tenant

from .models import (
    BrandingSettings, Subscription, TenantAuditLog,
)


def _log(action, instance, tenant=None):
    tenant = tenant or getattr(instance, 'tenant', None) or get_current_tenant()
    if tenant is None:
        return
    TenantAuditLog.objects.create(
        tenant=tenant,
        action=action,
        target_type=instance.__class__.__name__,
        target_id=str(getattr(instance, 'pk', '')),
    )


@receiver(post_save, sender=Subscription)
def log_subscription_save(sender, instance, created, **kwargs):
    _log('subscription.created' if created else 'subscription.updated', instance, instance.tenant)


@receiver(post_save, sender=BrandingSettings)
def log_branding_save(sender, instance, created, **kwargs):
    _log('branding.created' if created else 'branding.updated', instance, instance.tenant)


@receiver(post_delete, sender=Subscription)
def log_subscription_delete(sender, instance, **kwargs):
    _log('subscription.deleted', instance, instance.tenant)
