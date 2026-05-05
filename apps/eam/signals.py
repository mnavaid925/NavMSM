"""Audit signals + cross-module event emission for Module 10 - EAM.

Wires:
    - Audit entries on Asset, MaintenancePlan, PMSchedule, FailurePrediction,
      MaintenanceWorkOrder, Tool status transitions.
    - ConditionReading post_save: classify reading + auto-spawn FailurePrediction
      when status flips to 'critical' and no open prediction exists.
    - DowntimeEvent post_save: refresh parent MWO.downtime_minutes denorm.
    - Cross-module hook: mes.AndonAlert.post_save (type='equipment' + asset
      set + no open MWO) -> auto-create draft MaintenanceWorkOrder
      (wo_type='breakdown', source_andon=alert).
    - Cross-module hook: mes.ProductionReport.post_save when the parent
      MESWorkOrder.tool is set -> auto ToolUsageLog + atomic Tool denorm bump.

Per Lesson L-18, every connect() inside a factory or wired-lazily helper passes
weak=False so the inner closure receivers are not garbage-collected.
"""
import logging
from decimal import Decimal

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from apps.core.models import get_current_tenant

from .models import (
    Asset,
    ConditionReading,
    DowntimeEvent,
    FailurePrediction,
    MaintenancePlan,
    MaintenanceWorkOrder,
    PMSchedule,
    Tool,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit-log helper
# ---------------------------------------------------------------------------

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


def _stash(instance, sender, *fields):
    if instance.pk:
        try:
            prev = sender.all_objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            prev = None
        for f in fields:
            setattr(instance, f'_eam_prev_{f}', getattr(prev, f, None) if prev else None)
    else:
        for f in fields:
            setattr(instance, f'_eam_prev_{f}', None)


# ---------------------------------------------------------------------------
# Status-tracked resources (factory pattern - L-18 weak=False)
# ---------------------------------------------------------------------------

def _mk_status_signals(model, action_prefix):
    """Connect pre_save + post_save audit handlers for a status-tracked model.

    NOTE: pass weak=False to signal.connect() because the closure handlers
    defined inside this factory go out of scope after the function returns;
    the default weak-ref connection would let them be garbage-collected and
    the signals would never fire (Lesson L-18).
    """
    def _pre(sender, instance, **_):
        _stash(instance, sender, 'status')

    def _post(sender, instance, created, **_):
        if created:
            _tenant_audit(
                f'{action_prefix}.created', instance,
                meta={'status': getattr(instance, 'status', None)},
            )
            return
        prev = getattr(instance, '_eam_prev_status', None)
        if prev != instance.status:
            _tenant_audit(
                f'{action_prefix}.{instance.status}', instance,
                meta={'from': prev, 'to': instance.status},
            )

    pre_save.connect(_pre, sender=model, weak=False, dispatch_uid=f'{action_prefix}_pre')
    post_save.connect(_post, sender=model, weak=False, dispatch_uid=f'{action_prefix}_post')


_mk_status_signals(Asset, 'eam.asset')
_mk_status_signals(PMSchedule, 'eam.pm_schedule')
_mk_status_signals(FailurePrediction, 'eam.prediction')
_mk_status_signals(MaintenanceWorkOrder, 'eam.mwo')
_mk_status_signals(Tool, 'eam.tool')


@receiver(pre_save, sender=MaintenancePlan)
def maintenance_plan_pre(sender, instance, **_):
    _stash(instance, sender, 'is_active')


@receiver(post_save, sender=MaintenancePlan)
def maintenance_plan_post(sender, instance, created, **_):
    if created:
        _tenant_audit('eam.plan.created', instance, meta={'name': instance.name})
        return
    prev = getattr(instance, '_eam_prev_is_active', None)
    if prev is not None and prev != instance.is_active:
        action = 'eam.plan.activated' if instance.is_active else 'eam.plan.deactivated'
        _tenant_audit(action, instance, meta={'plan': instance.name})


# ---------------------------------------------------------------------------
# ConditionReading: classify + auto-spawn FailurePrediction on critical
# ---------------------------------------------------------------------------

@receiver(post_save, sender=ConditionReading)
def condition_reading_post(sender, instance, created, **_):
    """When a reading lands as 'critical' and no open prediction exists, spawn one."""
    if not created:
        return
    # Run the classifier now (writes status idempotently).
    from .services.prediction import check_reading
    cr = check_reading(instance)
    if cr.status != 'critical':
        return
    point = instance.point
    asset = point.asset
    open_qs = FailurePrediction.all_objects.filter(
        tenant=instance.tenant,
        asset=asset,
        status__in=('open', 'investigating'),
    )
    if open_qs.exists():
        return
    FailurePrediction.all_objects.create(
        tenant=instance.tenant,
        asset=asset,
        triggered_by_reading=instance,
        confidence_pct=Decimal('70'),
        summary=f'Reading on {point.name} crossed critical threshold',
        recommended_action='Investigate root cause and inspect the asset.',
        status='open',
    )


# ---------------------------------------------------------------------------
# DowntimeEvent: refresh MWO downtime denorm
# ---------------------------------------------------------------------------

@receiver(post_save, sender=DowntimeEvent)
def downtime_event_post(sender, instance, **_):
    if instance.mwo_id is None:
        return
    from .services.downtime import refresh_mwo_downtime
    try:
        refresh_mwo_downtime(instance.mwo)
    except Exception:  # pragma: no cover - keep the signal best-effort
        logger.warning('eam: failed to refresh MWO downtime denorm', exc_info=True)


# ---------------------------------------------------------------------------
# Cross-module hooks (lazy-wired)
# ---------------------------------------------------------------------------

def _stash_eam_x_prev(sender, instance, **_):
    """Stash prior status under our own attr so we don't depend on other apps' naming."""
    if instance.pk:
        try:
            prev = sender.all_objects.get(pk=instance.pk)
            instance._eam_x_prev_status = getattr(prev, 'status', None)
        except sender.DoesNotExist:
            instance._eam_x_prev_status = None
    else:
        instance._eam_x_prev_status = None


def _on_andon_for_equipment(sender, instance, created, **_):
    """When an equipment-type AndonAlert with an asset link is raised, draft a breakdown MWO.

    Idempotent via `source_andon` - if a MWO already references this alert, skip.
    """
    # Only fire on creation, otherwise every state change would respawn.
    if not created:
        return
    if getattr(instance, 'alert_type', None) != 'equipment':
        return
    asset = getattr(instance, 'asset', None)
    if asset is None:
        return
    existing = MaintenanceWorkOrder.all_objects.filter(source_andon=instance).first()
    if existing:
        return
    title = f'Equipment andon: {instance.title}'[:255]
    MaintenanceWorkOrder.all_objects.create(
        tenant=instance.tenant,
        asset=asset,
        wo_type='breakdown',
        priority='high' if instance.severity in ('high', 'critical') else 'medium',
        title=title,
        problem_description=instance.message or '',
        status='draft',
        reported_by=instance.raised_by,
        reported_at=instance.raised_at or timezone.now(),
        source_andon=instance,
    )


def _on_production_report_for_tool(sender, instance, created, **_):
    """When a ProductionReport is filed against an op whose work order has a tool set,
    emit a ToolUsageLog and bump the tool's denorms atomically.

    Idempotent via the (tool, mes_work_order, used_at) natural key inferred from
    the report's reported_at + work order. Re-firing on the same report would
    recompute, so we guard by checking for an existing log with the same
    mes_work_order + used_at.
    """
    if not created:
        return
    op = getattr(instance, 'work_order_operation', None)
    if op is None:
        return
    work_order = getattr(op, 'work_order', None)
    if work_order is None:
        return
    tool = getattr(work_order, 'tool', None)
    if tool is None:
        return
    from .models import ToolUsageLog
    used_at = instance.reported_at or timezone.now()
    cycles = int(instance.good_qty or 0) + int(instance.scrap_qty or 0)
    if cycles <= 0:
        return
    if ToolUsageLog.all_objects.filter(
        tool=tool, mes_work_order=work_order, used_at=used_at,
    ).exists():
        return
    from .services.tool_life import consume_usage_log
    consume_usage_log(
        tool,
        mes_work_order=work_order,
        cycles_added=cycles,
        operator=instance.reported_by,
        notes=f'Auto from production report #{instance.pk}',
    )


def _wire_cross_module_signals():
    try:
        from apps.mes.models import AndonAlert, ProductionReport
        post_save.connect(
            _on_andon_for_equipment,
            sender=AndonAlert,
            weak=False,
            dispatch_uid='eam_andon_to_mwo',
        )
        post_save.connect(
            _on_production_report_for_tool,
            sender=ProductionReport,
            weak=False,
            dispatch_uid='eam_production_report_to_tool_usage',
        )
    except Exception:  # pragma: no cover
        logger.warning('eam: apps.mes not loaded; skipping cross-module hooks')


_wire_cross_module_signals()
