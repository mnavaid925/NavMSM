"""Audit-log signal wiring for PLM models.

ECO status changes and ProductCompliance status changes both write to:
  - apps.tenants.TenantAuditLog (cross-cutting tenant audit feed)
  - apps.plm.ComplianceAuditLog (compliance-specific immutable trail)
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.core.models import get_current_tenant

from .models import EngineeringChangeOrder, ProductCompliance, ComplianceAuditLog


def _tenant_audit(action, instance, tenant=None, meta=None):
    # Lazy import to avoid circular deps at app init.
    from apps.tenants.models import TenantAuditLog
    tenant = tenant or getattr(instance, 'tenant', None) or get_current_tenant()
    if tenant is None:
        return
    TenantAuditLog.objects.create(
        tenant=tenant,
        action=action,
        target_type=instance.__class__.__name__,
        target_id=str(getattr(instance, 'pk', '')),
        meta=meta or {},
    )


# ---- ECO status tracking ----

@receiver(pre_save, sender=EngineeringChangeOrder)
def _stash_eco_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_status = sender.all_objects.get(pk=instance.pk).status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=EngineeringChangeOrder)
def log_eco_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit('eco.created', instance, instance.tenant,
                      meta={'number': instance.number, 'status': instance.status})
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status:
        _tenant_audit(
            f'eco.status.{instance.status}', instance, instance.tenant,
            meta={'number': instance.number, 'from': old, 'to': instance.status},
        )


# ---- Compliance status tracking ----

@receiver(pre_save, sender=ProductCompliance)
def _stash_compliance_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_status = sender.all_objects.get(pk=instance.pk).status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=ProductCompliance)
def log_compliance_save(sender, instance, created, **kwargs):
    if created:
        ComplianceAuditLog.objects.create(
            tenant=instance.tenant, compliance=instance, event='created',
            meta={'status': instance.status},
        )
        _tenant_audit('compliance.created', instance, instance.tenant,
                      meta={'product': instance.product.sku, 'standard': instance.standard.code})
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status:
        ComplianceAuditLog.objects.create(
            tenant=instance.tenant, compliance=instance, event='status_changed',
            meta={'from': old, 'to': instance.status},
        )
        _tenant_audit(
            f'compliance.status.{instance.status}', instance, instance.tenant,
            meta={'product': instance.product.sku, 'standard': instance.standard.code,
                  'from': old, 'to': instance.status},
        )
