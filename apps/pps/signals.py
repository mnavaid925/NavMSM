"""Audit-log signal wiring for PPS models.

Status transitions and apply/discard actions on MasterProductionSchedule,
ProductionOrder, Scenario, and OptimizationRun all write to
apps.tenants.TenantAuditLog. ScheduledOperation save/delete invalidates
CapacityLoad.computed_at for the affected work-center/date so the dashboard
shows the load as stale until recomputed.
"""
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.core.models import get_current_tenant

from .models import (
    CapacityLoad, MasterProductionSchedule, OptimizationRun, ProductionOrder,
    ScheduledOperation, Scenario,
)


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


def _stash_status(instance, sender):
    if instance.pk:
        try:
            instance._old_status = sender.all_objects.get(pk=instance.pk).status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


# ---- MPS status tracking ----

@receiver(pre_save, sender=MasterProductionSchedule)
def _stash_mps_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=MasterProductionSchedule)
def log_mps_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'mps.created', instance, instance.tenant,
            meta={'mps_number': instance.mps_number, 'status': instance.status},
        )
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status:
        _tenant_audit(
            f'mps.status.{instance.status}', instance, instance.tenant,
            meta={'mps_number': instance.mps_number, 'from': old, 'to': instance.status},
        )


# ---- Production order status tracking ----

@receiver(pre_save, sender=ProductionOrder)
def _stash_order_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=ProductionOrder)
def log_order_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'production_order.created', instance, instance.tenant,
            meta={'order_number': instance.order_number,
                  'product_id': instance.product_id,
                  'quantity': str(instance.quantity)},
        )
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status:
        _tenant_audit(
            f'production_order.status.{instance.status}', instance, instance.tenant,
            meta={'order_number': instance.order_number,
                  'from': old, 'to': instance.status},
        )


# ---- Scenario apply/discard tracking ----

@receiver(pre_save, sender=Scenario)
def _stash_scenario_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=Scenario)
def log_scenario_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'scenario.created', instance, instance.tenant,
            meta={'name': instance.name, 'base_mps_id': instance.base_mps_id},
        )
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status \
            and instance.status in ('applied', 'discarded', 'completed'):
        _tenant_audit(
            f'scenario.{instance.status}', instance, instance.tenant,
            meta={'name': instance.name, 'from': old, 'to': instance.status},
        )


# ---- Optimization run status tracking ----

@receiver(pre_save, sender=OptimizationRun)
def _stash_run_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=OptimizationRun)
def log_run_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'optimization.created', instance, instance.tenant,
            meta={'name': instance.name, 'objective_id': instance.objective_id},
        )
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status:
        _tenant_audit(
            f'optimization.{instance.status}', instance, instance.tenant,
            meta={'name': instance.name, 'from': old, 'to': instance.status},
        )


# ---- Scheduled operation save/delete -> invalidate capacity load ----

def _invalidate_load(scheduled_op):
    CapacityLoad.all_objects.filter(
        work_center=scheduled_op.work_center_id,
        period_date=scheduled_op.planned_start.date(),
    ).update(computed_at=None)


@receiver(post_save, sender=ScheduledOperation)
def scheduled_op_saved(sender, instance, **kwargs):
    _invalidate_load(instance)


@receiver(post_delete, sender=ScheduledOperation)
def scheduled_op_deleted(sender, instance, **kwargs):
    _invalidate_load(instance)
