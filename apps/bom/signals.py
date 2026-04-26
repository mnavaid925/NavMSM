"""Audit-log signal wiring for BOM models.

BillOfMaterials status transitions and AlternateMaterial approval changes
write to apps.tenants.TenantAuditLog. BOMLine save/delete invalidates the
parent BOM's cost rollup (so the UI shows it as stale).
"""
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.core.models import get_current_tenant

from .models import AlternateMaterial, BillOfMaterials, BOMCostRollup, BOMLine


def _tenant_audit(action, instance, tenant=None, meta=None):
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


# ---- BOM status tracking ----

@receiver(pre_save, sender=BillOfMaterials)
def _stash_bom_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_status = sender.all_objects.get(pk=instance.pk).status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=BillOfMaterials)
def _enforce_single_default(sender, instance, **kwargs):
    """When a BOM is saved with is_default=True, demote any other BOM of the
    same (tenant, product, bom_type) so the rollup-cascade pick is deterministic.
    """
    if not instance.is_default or instance.tenant_id is None:
        return
    sender.all_objects.filter(
        tenant=instance.tenant,
        product=instance.product,
        bom_type=instance.bom_type,
        is_default=True,
    ).exclude(pk=instance.pk).update(is_default=False)


@receiver(post_save, sender=BillOfMaterials)
def log_bom_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'bom.created', instance, instance.tenant,
            meta={'bom_number': instance.bom_number, 'status': instance.status,
                  'bom_type': instance.bom_type},
        )
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status:
        _tenant_audit(
            f'bom.status.{instance.status}', instance, instance.tenant,
            meta={'bom_number': instance.bom_number, 'from': old, 'to': instance.status},
        )


# ---- Alternate approval tracking ----

@receiver(pre_save, sender=AlternateMaterial)
def _stash_alt_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_approval = sender.all_objects.get(pk=instance.pk).approval_status
        except sender.DoesNotExist:
            instance._old_approval = None
    else:
        instance._old_approval = None


@receiver(post_save, sender=AlternateMaterial)
def log_alternate_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'alternate.created', instance, instance.tenant,
            meta={'bom_line_id': instance.bom_line_id,
                  'alternate_sku': instance.alternate_component.sku,
                  'status': instance.approval_status},
        )
        return
    old = getattr(instance, '_old_approval', None)
    if old is not None and old != instance.approval_status:
        _tenant_audit(
            f'alternate.{instance.approval_status}', instance, instance.tenant,
            meta={'alternate_sku': instance.alternate_component.sku,
                  'from': old, 'to': instance.approval_status},
        )


# ---- BOMLine change → invalidate rollup ----

def _invalidate_rollup(line):
    BOMCostRollup.all_objects.filter(bom=line.bom_id).update(computed_at=None)


@receiver(post_save, sender=BOMLine)
def line_saved_invalidates_rollup(sender, instance, **kwargs):
    _invalidate_rollup(instance)


@receiver(post_delete, sender=BOMLine)
def line_deleted_invalidates_rollup(sender, instance, **kwargs):
    _invalidate_rollup(instance)
