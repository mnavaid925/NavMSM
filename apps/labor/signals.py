"""Module 11 - Labor & Workforce Management signals.

Wires:
    * Status-transition audit logging via the same factory pattern used in
      procurement / EAM. **Lesson L-18:** every connect() uses ``weak=False``
      so closures created inside the factory are not garbage-collected.
    * Cross-module hooks (additive, idempotent):
        - mes.OperatorTimeLog.post_save (clock_in/out)  -> AttendanceRecord
        - mes.OperatorTimeLog.post_save (stop_job)      -> direct LaborBooking
        - eam.MWOLaborLog.post_save                     -> indirect LaborBooking
        - mes.ProductionReport.post_save                -> IncentiveLine accumulation
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from . import models

# In-memory snapshot store keyed on ``(model, pk)`` -> previous status. Mirrors
# the procurement / EAM pattern. See Lesson L-18.
_pre_status_snapshots: dict = {}


def _audit(action: str, instance, extra: dict | None = None):
    """Audit hook stub - tenants.TenantAuditLog.write() is the canonical sink.

    Importing tenants.models here would create a circular import at app-load,
    so we resolve it lazily on first call.
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
    """Factory: bind pre/post-save status snapshot + audit emit on transitions.

    Lesson L-18: every connect() uses weak=False so the inner closures are not
    garbage-collected after the factory returns.
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
        dispatch_uid=f'labor.{action_prefix}.pre_save',
    )
    post_save.connect(
        _post, sender=model_cls, weak=False,
        dispatch_uid=f'labor.{action_prefix}.post_save',
    )


# ----------------------------------------------------------------------------
# Audit registrations
# ----------------------------------------------------------------------------
_mk_status_signals(models.Employee, 'labor.employee')
_mk_status_signals(models.LeaveRequest, 'labor.leave')
_mk_status_signals(models.IncentiveRun, 'labor.incentive_run')
_mk_status_signals(models.IncentivePeriod, 'labor.period')
_mk_status_signals(models.CompetencyAssessment, 'labor.assessment')
_mk_status_signals(models.TrainingPlan, 'labor.training_plan')
_mk_status_signals(models.EmployeeCertification, 'labor.cert')


# ----------------------------------------------------------------------------
# Cross-module hooks
# ----------------------------------------------------------------------------

def _resolve_employee_from_operator(operator) -> models.Employee | None:
    """ShopFloorOperator -> Employee soft link. Returns None if unlinked."""
    employee = getattr(operator, 'employee', None)
    if employee is None:
        return None
    return employee


@receiver(post_save, sender='mes.OperatorTimeLog', dispatch_uid='labor.timelog_to_attendance', weak=False)
def mes_timelog_to_attendance(sender, instance, created, **kwargs):
    """Clock-in / clock-out -> upsert today's AttendanceRecord."""
    if instance.action not in ('clock_in', 'clock_out'):
        return
    employee = _resolve_employee_from_operator(instance.operator)
    if employee is None:
        return
    work_date = instance.recorded_at.date() if instance.recorded_at else timezone.now().date()
    rec, _ = models.AttendanceRecord.all_objects.get_or_create(
        tenant_id=instance.tenant_id,
        employee=employee,
        work_date=work_date,
        defaults={'status': 'present'},
    )
    if instance.action == 'clock_in':
        if rec.clock_in_at is None or instance.recorded_at < rec.clock_in_at:
            rec.clock_in_at = instance.recorded_at
    else:  # clock_out
        if rec.clock_out_at is None or instance.recorded_at > rec.clock_out_at:
            rec.clock_out_at = instance.recorded_at
    if rec.clock_in_at and rec.clock_out_at:
        delta = rec.clock_out_at - rec.clock_in_at
        rec.worked_minutes = max(0, int(delta.total_seconds() // 60))
    rec.save()


def _lookup_rate_for(employee, at_dt) -> Decimal:
    """Pure helper - return the LaborRate.hourly_rate effective at ``at_dt``."""
    at_date = at_dt.date() if hasattr(at_dt, 'date') else at_dt
    qs = models.LaborRate.all_objects.filter(
        tenant_id=employee.tenant_id, employee=employee,
        effective_from__lte=at_date,
    )
    qs = qs.filter(
        effective_to__isnull=True,
    ) | qs.filter(effective_to__gte=at_date)
    rate = qs.order_by('-effective_from').first()
    return rate.hourly_rate if rate else Decimal('0')


@receiver(post_save, sender='mes.OperatorTimeLog', dispatch_uid='labor.timelog_to_booking', weak=False)
def mes_timelog_to_booking(sender, instance, created, **kwargs):
    """Stop-job -> direct LaborBooking against the order's product cost center.

    Idempotent via (source_time_log, kind='direct') natural key.
    """
    if instance.action != 'stop_job':
        return
    if not created:
        return  # only emit once per stop_job event
    op = instance.work_order_operation
    if op is None:
        return
    employee = _resolve_employee_from_operator(instance.operator)
    if employee is None:
        return
    if models.LaborBooking.all_objects.filter(
        source_time_log=instance, kind='direct',
    ).exists():
        return

    # Find the most recent matching start_job/resume_job to compute elapsed minutes.
    prior = (
        sender.all_objects
        .filter(operator=instance.operator, work_order_operation=op,
                action__in=('start_job', 'resume_job'),
                recorded_at__lte=instance.recorded_at)
        .order_by('-recorded_at')
        .first()
    )
    if prior is None:
        return
    minutes = max(1, int((instance.recorded_at - prior.recorded_at).total_seconds() // 60))

    cc = None
    try:
        product = op.work_order.production_order.product
        cc = getattr(product, 'cost_center', None)
    except AttributeError:
        cc = None

    rate = _lookup_rate_for(employee, instance.recorded_at)
    with transaction.atomic():
        models.LaborBooking.objects.create(
            tenant_id=instance.tenant_id,
            employee=employee,
            kind='direct',
            cost_center=cc,
            worked_at=instance.recorded_at,
            minutes=minutes,
            hourly_rate_snapshot=rate,
            source_type='mes_time_log',
            source_time_log=instance,
        )


@receiver(post_save, sender='eam.MWOLaborLog', dispatch_uid='labor.mwo_to_booking', weak=False)
def eam_mwo_labor_to_booking(sender, instance, created, **kwargs):
    """MWO labor -> indirect LaborBooking against the asset's cost center.

    Idempotent via (source_mwo_labor, kind='indirect') natural key.
    """
    if not created:
        return
    if not instance.minutes or instance.minutes <= 0:
        return
    if models.LaborBooking.all_objects.filter(
        source_mwo_labor=instance, kind='indirect',
    ).exists():
        return

    # eam.MWOLaborLog.technician is the User FK; resolve back to a labor.Employee.
    employee = None
    user = getattr(instance, 'technician', None)
    if user is not None:
        employee = models.Employee.all_objects.filter(
            tenant_id=instance.tenant_id, user_id=user.id,
        ).first()
    if employee is None:
        return

    cc = None
    try:
        cc = getattr(instance.mwo.asset, 'cost_center', None)
    except AttributeError:
        cc = None

    started_at = instance.started_at or timezone.now()
    rate = _lookup_rate_for(employee, started_at)
    with transaction.atomic():
        models.LaborBooking.objects.create(
            tenant_id=instance.tenant_id,
            employee=employee,
            kind='indirect',
            cost_center=cc,
            worked_at=started_at,
            minutes=int(instance.minutes),
            hourly_rate_snapshot=rate,
            source_type='eam_mwo_labor',
            source_mwo_labor=instance,
        )


@receiver(post_save, sender='mes.ProductionReport', dispatch_uid='labor.report_to_incentive', weak=False)
def mes_report_to_incentive(sender, instance, created, **kwargs):
    """ProductionReport -> accumulate IncentiveLine for matching open run.

    Idempotent via M2M membership check on IncentiveLine.production_reports.
    """
    if not created:
        return
    good = instance.good_qty or Decimal('0')
    if good <= 0:
        return
    operator = None
    try:
        op = instance.work_order_operation
        product = op.work_order.production_order.product
        # Prefer reported_by user -> employee
        user = getattr(instance, 'reported_by', None)
        if user is None:
            return
        employee = models.Employee.all_objects.filter(
            tenant_id=instance.tenant_id, user_id=user.id,
        ).first()
        if employee is None:
            return
    except AttributeError:
        return

    today = (instance.reported_at or timezone.now()).date()
    runs = models.IncentiveRun.all_objects.filter(
        tenant_id=instance.tenant_id, status='draft',
        period__start_date__lte=today, period__end_date__gte=today,
    ).select_related('scheme', 'period')
    for run in runs:
        if run.scheme.applicable_products.exists():
            if not run.scheme.applicable_products.filter(pk=product.pk).exists():
                continue
        # Resolve the rate
        rate_qs = run.scheme.piece_rates.filter(product=product) if product else None
        rate_row = rate_qs.first() if rate_qs is not None else None
        if rate_row is None:
            continue
        with transaction.atomic():
            line, _ = models.IncentiveLine.all_objects.get_or_create(
                tenant_id=instance.tenant_id, run=run, employee=employee,
                defaults={'rate_applied': rate_row.rate_per_unit},
            )
            if line.production_reports.filter(pk=instance.pk).exists():
                continue
            line.production_reports.add(instance)
            line.qualifying_units = (line.qualifying_units or Decimal('0')) + good
            line.rate_applied = rate_row.rate_per_unit
            line.save()
            run.total_amount = sum((l.amount for l in run.lines.all()), Decimal('0'))
            run.save(update_fields=['total_amount', 'updated_at'])
