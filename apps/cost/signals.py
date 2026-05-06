"""Module 12 - Cost Management & Accounting signals.

Wires:
    * Status-transition audit logging via the same factory pattern used in
      procurement / EAM / labor. Lesson L-18: every connect() uses
      ``weak=False`` so closures created inside the factory are not GC'd.
    * Cross-module hooks (additive, idempotent):
        - labor.LaborBooking.post_save (kind='direct')   -> WIPEntry(labor_applied)
        - labor.LaborBooking.post_save (kind='indirect') -> OverheadActualPool accum
        - labor.LaborBooking.pre_delete                  -> reverse direct WIPEntry
        - mes.ProductionReport.post_save (good_qty>0)    -> WIPEntry(completion)
        - mes.ProductionReport.pre_delete                -> reverse completion entry

Idempotency: every cross-module hook keys on the source FK + entry_type unique
constraints declared on WIPEntry.Meta.constraints.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from . import models as cm
from .services import wip as wip_svc
from .services import overhead as oh_svc

_pre_status_snapshots: dict = {}


def _audit(action: str, instance, extra: dict | None = None):
    """Audit hook stub - tenants.TenantAuditLog.write() is the canonical sink.

    Importing tenants.models eagerly would create a circular import.
    """
    try:
        from apps.tenants.models import TenantAuditLog
    except ImportError:
        return
    if getattr(instance, 'tenant_id', None) is None:
        return
    payload = {'pk': instance.pk}
    if extra:
        payload.update(extra)
    try:
        TenantAuditLog.objects.create(
            tenant_id=instance.tenant_id,
            action=action,
            target_type=instance.__class__.__name__,
            target_id=str(instance.pk),
            payload=payload,
        )
    except Exception:
        # Audit must never break a write path.
        pass


def _mk_status_signals(model_cls, action_prefix: str):
    """Bind pre/post-save status snapshot + audit emit on transitions.

    Lesson L-18: every connect() uses weak=False.
    """

    def _pre(sender, instance, **kwargs):
        if not instance.pk:
            return
        try:
            prev = sender.all_objects.only('status').get(pk=instance.pk).status
        except sender.DoesNotExist:
            return
        _pre_status_snapshots[(sender, instance.pk)] = prev

    def _post(sender, instance, created, **kwargs):
        prev = _pre_status_snapshots.pop((sender, instance.pk), None)
        if created:
            _audit(f'{action_prefix}.created', instance, {'status': instance.status})
            return
        if prev is not None and prev != instance.status:
            _audit(
                f'{action_prefix}.{instance.status}',
                instance,
                {'previous_status': prev, 'status': instance.status},
            )

    pre_save.connect(
        _pre, sender=model_cls, weak=False,
        dispatch_uid=f'cost.{action_prefix}.pre_save',
    )
    post_save.connect(
        _post, sender=model_cls, weak=False,
        dispatch_uid=f'cost.{action_prefix}.post_save',
    )


# ----------------------------------------------------------------------------
# Audit registrations
# ----------------------------------------------------------------------------
_mk_status_signals(cm.StandardCostVersion, 'cost.std_version')
_mk_status_signals(cm.AccountingPeriod, 'cost.period')
_mk_status_signals(cm.JobCost, 'cost.job')


# ----------------------------------------------------------------------------
# Cross-module hooks
# ----------------------------------------------------------------------------

def _resolve_po_from_labor_booking(booking):
    """Walk LaborBooking -> source_time_log -> work_order_operation.work_order.production_order.

    Returns the ProductionOrder or None.
    """
    tl = getattr(booking, 'source_time_log', None)
    if tl is None:
        return None
    op = getattr(tl, 'work_order_operation', None)
    if op is None:
        return None
    wo = getattr(op, 'work_order', None)
    if wo is None:
        return None
    return getattr(wo, 'production_order', None)


def _ensure_job(production_order):
    """Get-or-create the JobCost for a production order. Returns the JobCost."""
    if production_order is None:
        return None
    job, _ = cm.JobCost.all_objects.get_or_create(
        tenant_id=production_order.tenant_id,
        production_order=production_order,
        defaults={'status': 'open'},
    )
    return job


def _find_period_for(tenant_id, when_date):
    """Find an open AccountingPeriod whose date range contains ``when_date``."""
    return cm.AccountingPeriod.all_objects.filter(
        tenant_id=tenant_id,
        start_date__lte=when_date, end_date__gte=when_date,
        status='open',
    ).first()


def _find_default_indirect_pool(tenant_id):
    """Return a fallback overhead pool to absorb indirect labor (first active)."""
    return cm.OverheadPool.all_objects.filter(
        tenant_id=tenant_id, is_active=True,
    ).order_by('id').first()


@receiver(post_save, sender='labor.LaborBooking',
          dispatch_uid='cost.labor_booking_to_wip', weak=False)
def labor_booking_to_wip(sender, instance, created, **kwargs):
    """LaborBooking.post_save -> emit WIPEntry(labor_applied) for direct, or
    accumulate into OverheadActualPool for indirect.

    Idempotent via WIPEntry.Meta unique constraint
    ``(source_labor_booking, entry_type)``.
    """
    if not created:
        return
    if instance.kind == 'direct':
        po = _resolve_po_from_labor_booking(instance)
        if po is None:
            return
        job = _ensure_job(po)
        if job is None:
            return
        # Idempotent guard: skip if already emitted.
        if cm.WIPEntry.all_objects.filter(
            source_labor_booking=instance, entry_type='labor_applied',
        ).exists():
            return
        wip_svc.post_wip_entry(
            tenant=instance.tenant,
            job=job,
            entry_type='labor_applied',
            amount=instance.total_cost or Decimal('0'),
            quantity=Decimal(instance.minutes) / Decimal('60') if instance.minutes else Decimal('0'),
            unit_of_measure='hours',
            cost_center=instance.cost_center,
            source_labor_booking=instance,
        )
    elif instance.kind == 'indirect':
        period = _find_period_for(instance.tenant_id, instance.worked_at.date())
        if period is None:
            return
        pool = _find_default_indirect_pool(instance.tenant_id)
        if pool is None:
            return
        oh_svc.accumulate_indirect_labor(
            period, pool, instance.total_cost or Decimal('0')
        )


@receiver(pre_delete, sender='labor.LaborBooking',
          dispatch_uid='cost.labor_booking_to_wip_reverse', weak=False)
def labor_booking_to_wip_reverse(sender, instance, **kwargs):
    """LaborBooking.pre_delete -> reverse the matching WIPEntry."""
    entry = cm.WIPEntry.all_objects.filter(
        source_labor_booking=instance, entry_type='labor_applied', is_reversal=False,
    ).first()
    if entry is None:
        return
    try:
        wip_svc.reverse_wip_entry(entry, reason='labor-booking-deleted')
    except Exception:
        pass


@receiver(post_save, sender='mes.ProductionReport',
          dispatch_uid='cost.report_to_wip_completion', weak=False)
def report_to_wip_completion(sender, instance, created, **kwargs):
    """ProductionReport.post_save -> WIPEntry(completion) at standard cost.

    Idempotent via WIPEntry constraint ``(source_production_report, entry_type)``.
    """
    if not created:
        return
    good = instance.good_qty or Decimal('0')
    if good <= 0:
        return
    op = getattr(instance, 'work_order_operation', None)
    if op is None:
        return
    wo = getattr(op, 'work_order', None)
    if wo is None:
        return
    po = getattr(wo, 'production_order', None)
    if po is None:
        return
    job = _ensure_job(po)
    if job is None:
        return
    if cm.WIPEntry.all_objects.filter(
        source_production_report=instance, entry_type='completion',
    ).exists():
        return
    # Look up the active standard cost.
    version = cm.StandardCostVersion.all_objects.filter(
        tenant_id=instance.tenant_id, status='active',
    ).order_by('-effective_from').first()
    std_per_unit = Decimal('0')
    if version is not None:
        sc = cm.StandardCost.all_objects.filter(
            version=version, product=po.product,
        ).first()
        if sc is not None:
            std_per_unit = sc.total_cost or Decimal('0')
    if std_per_unit <= 0:
        return  # No active standard yet; skip silently.
    amount = (Decimal(good) * std_per_unit).quantize(Decimal('0.01'))
    wip_svc.post_wip_entry(
        tenant_id=instance.tenant_id, tenant=instance.tenant,
        job=job,
        entry_type='completion',
        amount=amount,
        quantity=good,
        unit_of_measure=getattr(po.product, 'unit_of_measure', '') or '',
        routing_operation=getattr(op, 'routing_operation', None),
        source_production_report=instance,
    )


@receiver(pre_delete, sender='mes.ProductionReport',
          dispatch_uid='cost.report_to_wip_completion_reverse', weak=False)
def report_to_wip_completion_reverse(sender, instance, **kwargs):
    entry = cm.WIPEntry.all_objects.filter(
        source_production_report=instance, entry_type='completion', is_reversal=False,
    ).first()
    if entry is None:
        return
    try:
        wip_svc.reverse_wip_entry(entry, reason='production-report-deleted')
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Internal: WIPEntry pre_delete keeps JobCost denorms consistent
# ----------------------------------------------------------------------------

@receiver(pre_delete, sender=cm.WIPEntry,
          dispatch_uid='cost.wip_entry_pre_delete', weak=False)
def wip_entry_pre_delete(sender, instance, **kwargs):
    """Roll back JobCost denorms when a WIPEntry is hard-deleted.

    Reversal entries (``is_reversal=True``) are already offset, so deleting one
    likewise offsets in the opposite direction.
    """
    job = instance.job
    if job is None:
        return
    field_map = {
        'material_issued': 'total_material',
        'labor_applied': 'total_labor',
        'overhead_applied': 'total_overhead',
        'completion': 'total_completion_credit',
        'variance': 'total_overhead',
        'adjustment': 'total_overhead',
    }
    field = field_map.get(instance.entry_type)
    if field is None:
        return
    with transaction.atomic():
        cm.JobCost.all_objects.filter(pk=job.pk).update(
            **{field: getattr(job, field) - (instance.amount or Decimal('0'))}
        )
        job.refresh_from_db()
        job.recompute_balance()
        job.save(update_fields=['wip_balance', 'updated_at'])
