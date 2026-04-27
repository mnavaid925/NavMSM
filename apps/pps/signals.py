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
    CapacityCalendar, CapacityLoad, MasterProductionSchedule, OptimizationRun,
    ProductionOrder, Routing, RoutingOperation, ScheduledOperation, Scenario,
    WorkCenter,
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


# ---- Configuration mutations -> audit log (D-11) ----
#
# Routing, RoutingOperation, WorkCenter, and CapacityCalendar changes are
# operationally significant — a tenant admin must be able to reconstruct who
# changed a work center's capacity or removed a routing. The signals emit
# `<entity>.created` / `<entity>.updated` / `<entity>.deleted` audit rows.

def _audit_config_save(action_prefix, instance, created, **fields):
    label = 'created' if created else 'updated'
    _tenant_audit(
        f'{action_prefix}.{label}', instance, instance.tenant,
        meta={'pk': instance.pk, **fields},
    )


def _audit_config_delete(action_prefix, instance, **fields):
    _tenant_audit(
        f'{action_prefix}.deleted', instance, instance.tenant,
        meta={'pk': instance.pk, **fields},
    )


@receiver(post_save, sender=Routing)
def log_routing_save(sender, instance, created, **kwargs):
    _audit_config_save(
        'routing', instance, created,
        routing_number=instance.routing_number,
        product_id=instance.product_id, version=instance.version,
        status=instance.status,
    )


@receiver(post_delete, sender=Routing)
def log_routing_delete(sender, instance, **kwargs):
    _audit_config_delete(
        'routing', instance,
        routing_number=instance.routing_number,
        product_id=instance.product_id, version=instance.version,
    )


@receiver(post_save, sender=RoutingOperation)
def log_routing_operation_save(sender, instance, created, **kwargs):
    _audit_config_save(
        'routing_operation', instance, created,
        routing_id=instance.routing_id, sequence=instance.sequence,
        operation_name=instance.operation_name,
        work_center_id=instance.work_center_id,
    )


@receiver(post_delete, sender=RoutingOperation)
def log_routing_operation_delete(sender, instance, **kwargs):
    _audit_config_delete(
        'routing_operation', instance,
        routing_id=instance.routing_id, sequence=instance.sequence,
        operation_name=instance.operation_name,
    )


@receiver(post_save, sender=WorkCenter)
def log_work_center_save(sender, instance, created, **kwargs):
    _audit_config_save(
        'work_center', instance, created,
        code=instance.code, name=instance.name,
        work_center_type=instance.work_center_type,
        is_active=instance.is_active,
    )


@receiver(post_delete, sender=WorkCenter)
def log_work_center_delete(sender, instance, **kwargs):
    _audit_config_delete(
        'work_center', instance, code=instance.code, name=instance.name,
    )


@receiver(post_save, sender=CapacityCalendar)
def log_capacity_calendar_save(sender, instance, created, **kwargs):
    _audit_config_save(
        'capacity_calendar', instance, created,
        work_center_id=instance.work_center_id,
        day_of_week=instance.day_of_week,
        shift_start=str(instance.shift_start),
        shift_end=str(instance.shift_end),
        is_working=instance.is_working,
    )


@receiver(post_delete, sender=CapacityCalendar)
def log_capacity_calendar_delete(sender, instance, **kwargs):
    _audit_config_delete(
        'capacity_calendar', instance,
        work_center_id=instance.work_center_id,
        day_of_week=instance.day_of_week,
        shift_start=str(instance.shift_start),
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
