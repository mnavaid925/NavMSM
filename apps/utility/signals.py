"""Module 14 - Energy & Utility Management signals.

Wires:
    * Status-transition audit logging via the same factory pattern used in
      cost / eam / labor (Lesson L-18: every connect() inside a factory
      passes ``weak=False`` so closure handlers aren't garbage-collected).
      Action prefixes follow ``utility.<resource>.<status>``:
          - utility.allocation.<status>     (UtilityAllocation)
          - utility.dre.<status>            (DemandResponseEvent)
          - utility.carbon.<status>         (CarbonEmission)
          - utility.peak_suggestion.<status>(PeakShavingSuggestion - bonus)
    * Cross-module hooks (additive, idempotent):
        - eam.AssetMeterReading.post_save (meter_type='kwh')
              -> utility.UtilityConsumption (idempotent on source_meter_reading)
        - eam.AssetMeterReading.pre_delete
              -> reversal UtilityConsumption row (negative consumption / cost)
        - utility.UtilityConsumption.post_save
              -> utility.CarbonEmission (idempotent on source_consumption)
        - utility.UtilityConsumption.pre_delete
              -> reversal CarbonEmission row (negative co2e / source_quantity)

Idempotency: every cross-module hook keys on the source FK unique constraint
declared on UtilityConsumption.Meta.constraints / CarbonEmission.Meta.constraints.
Reversal pattern mirrors apps.inventory.signals + apps.cost.services.wip:
emit a NEW row with the ``is_reversal=True`` flag and negated quantities,
rather than mutating or deleting the original.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models.signals import post_save, pre_delete, pre_save
from django.utils import timezone

from . import models as um


_pre_status_snapshots: dict = {}
_log = logging.getLogger(__name__)


def _audit(action: str, instance, extra: dict | None = None):
    """Audit hook — tenants.TenantAuditLog is the canonical sink.

    Importing tenants.models eagerly would create a circular import.
    Audit must never break a write path, hence the broad try/except —
    but per D-09, we log a warning rather than swallow silently so
    audit-pipeline regressions are observable.
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
            meta=payload,
        )
    except Exception as exc:
        # D-09: surface (don't crash, but don't swallow either).
        _log.warning(
            'utility audit emit failed: action=%s target=%s pk=%s err=%s',
            action, instance.__class__.__name__, instance.pk, exc,
            exc_info=True,
        )


def _mk_status_signals(model_cls, action_prefix: str):
    """Bind pre/post-save status snapshot + audit emit on transitions.

    Lesson L-18: every connect() uses weak=False because the closure
    receivers defined here go out of scope when the factory returns; the
    default weak-ref connection would let them be garbage-collected and the
    signals would never fire.
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
            _audit(
                f'utility.{action_prefix}.created', instance,
                {'status': getattr(instance, 'status', None)},
            )
            return
        if prev is not None and prev != getattr(instance, 'status', None):
            _audit(
                f'utility.{action_prefix}.{instance.status}',
                instance,
                {'previous_status': prev, 'status': instance.status},
            )

    pre_save.connect(
        _pre, sender=model_cls, weak=False,
        dispatch_uid=f'utility.{action_prefix}.pre_save',
    )
    post_save.connect(
        _post, sender=model_cls, weak=False,
        dispatch_uid=f'utility.{action_prefix}.post_save',
    )


def _mk_flag_signals(model_cls, action_prefix: str, flag_field: str,
                     true_action: str, false_action: str):
    """Bind pre/post-save audit on a boolean flag transition.

    UtilityAllocation has no ``status`` field — its workflow is captured by
    ``is_posted_to_cost`` and ``is_reversed``. We treat ``is_posted_to_cost``
    flips as the canonical 'posted'/'unposted' transitions.
    """

    snap_key = f'_utility_prev_{flag_field}'

    def _pre(sender, instance, **kwargs):
        if not instance.pk:
            return
        try:
            prev = getattr(
                sender.all_objects.only(flag_field).get(pk=instance.pk),
                flag_field,
            )
        except sender.DoesNotExist:
            return
        _pre_status_snapshots[(sender, instance.pk, snap_key)] = prev

    def _post(sender, instance, created, **kwargs):
        prev = _pre_status_snapshots.pop((sender, instance.pk, snap_key), None)
        cur = getattr(instance, flag_field, None)
        if created:
            _audit(
                f'utility.{action_prefix}.created', instance,
                {flag_field: cur},
            )
            return
        if prev is not None and prev != cur:
            action = true_action if cur else false_action
            _audit(
                f'utility.{action_prefix}.{action}', instance,
                {'previous': prev, 'current': cur},
            )

    pre_save.connect(
        _pre, sender=model_cls, weak=False,
        dispatch_uid=f'utility.{action_prefix}.{flag_field}.pre_save',
    )
    post_save.connect(
        _post, sender=model_cls, weak=False,
        dispatch_uid=f'utility.{action_prefix}.{flag_field}.post_save',
    )


# ----------------------------------------------------------------------------
# Audit registrations (spec: UtilityAllocation, DemandResponseEvent, CarbonEmission)
# ----------------------------------------------------------------------------

# UtilityAllocation has no status field; track its is_posted_to_cost flag
# (posted / unposted) so audit captures the canonical workflow transition.
_mk_flag_signals(
    um.UtilityAllocation, 'allocation',
    flag_field='is_posted_to_cost',
    true_action='posted', false_action='unposted',
)

_mk_status_signals(um.DemandResponseEvent, 'dre')

# CarbonEmission has no status field either; treat its is_reversal flip as
# the auditable workflow event ('reversed').
_mk_flag_signals(
    um.CarbonEmission, 'carbon',
    flag_field='is_reversal',
    true_action='reversed', false_action='unreversed',
)

# Bonus: PeakShavingSuggestion has a real status workflow worth auditing too.
_mk_status_signals(um.PeakShavingSuggestion, 'peak_suggestion')


# ----------------------------------------------------------------------------
# Cross-module hook 1 - eam.AssetMeterReading -> UtilityConsumption
# ----------------------------------------------------------------------------

def _on_meter_reading_save(sender, instance, created, **kwargs):
    """Auto-emit a UtilityConsumption row when a kWh AssetMeterReading is recorded.

    Strategy:
        - Only fires for meter_type='kwh' (other meter types stay EAM-only).
        - Looks up an active UtilityMeter linked via asset FK + electricity type
          for the same tenant.
        - Computes a 1-hour window ending at recorded_at.
        - Idempotent on partial unique constraint (source_meter_reading)
          enforced inside ``services.meters.post_consumption``.
        - Silently skips when no matching active electricity meter exists,
          or when this isn't a fresh creation (edits should not respawn rows).
    """
    if not created:
        return
    if (instance.meter_type or '').lower() != 'kwh':
        return
    if instance.tenant_id is None or instance.asset_id is None:
        return
    meter = um.UtilityMeter.all_objects.filter(
        tenant_id=instance.tenant_id,
        asset_id=instance.asset_id,
        utility_type__code__iexact='electricity',
        is_active=True,
    ).first()
    if meter is None:
        return
    # Idempotent guard: another worker may have raced ahead.
    if um.UtilityConsumption.all_objects.filter(
        source_meter_reading=instance,
    ).exists():
        return
    end = instance.recorded_at or timezone.now()
    start = end - timedelta(hours=1)
    prev = (
        instance.__class__.all_objects
        .filter(
            tenant_id=instance.tenant_id, asset_id=instance.asset_id,
            meter_type='kwh',
        )
        .exclude(pk=instance.pk)
        .order_by('-recorded_at')
        .first()
    )
    start_reading = prev.reading_value if prev else (instance.reading_value or Decimal('0'))
    end_reading = instance.reading_value or Decimal('0')
    try:
        from apps.utility.services import meters as meter_svc
        with transaction.atomic():
            meter_svc.post_consumption(
                meter,
                period_start=start,
                period_end=end,
                start_reading=start_reading,
                end_reading=end_reading,
                source='eam_meter',
                source_meter_reading=instance,
            )
    except Exception:
        # Auto-feed is best-effort; never break the EAM write path.
        pass


def _on_meter_reading_delete(sender, instance, **kwargs):
    """Reverse the matching UtilityConsumption row when its source reading is deleted.

    Mirrors apps.inventory.signals._on_production_report_delete: emit a NEW
    reversal row (``is_reversal=True``, negative consumption + total_cost)
    rather than mutating or deleting the original. The original keeps its
    audit value; the reversal nets it out in downstream rollups.

    pre_delete (not post_delete): on_delete=SET_NULL on
    UtilityConsumption.source_meter_reading clears the FK during deletion,
    so by the time post_delete fires we cannot locate the original.
    """
    if (instance.meter_type or '').lower() != 'kwh':
        return
    original = um.UtilityConsumption.all_objects.filter(
        source_meter_reading=instance, is_reversal=False,
    ).first()
    if original is None:
        return
    # Idempotent guard: don't double-reverse.
    if um.UtilityConsumption.all_objects.filter(
        tenant_id=original.tenant_id,
        meter=original.meter,
        is_reversal=True,
        notes__startswith=f'reversal-of:{original.entry_number}',
    ).exists():
        return
    try:
        with transaction.atomic():
            # Build a mirror-image row. Negate consumption + total_cost via
            # swapped start/end readings so the model's save() math produces
            # zero delta; then explicitly negate the persisted columns after.
            reversal = um.UtilityConsumption.all_objects.create(
                tenant=original.tenant,
                meter=original.meter,
                period_start=original.period_start,
                period_end=original.period_end,
                start_reading=original.end_reading,
                end_reading=original.start_reading,
                unit_cost=original.unit_cost,
                source=original.source,
                source_meter_reading=None,
                recorded_at=timezone.now(),
                is_reversal=True,
                notes=f'reversal-of:{original.entry_number} (eam reading deleted)',
            )
            # Force the negated values explicitly — the model's save() clamps
            # negative deltas to zero, so we override here for a clean offset.
            um.UtilityConsumption.all_objects.filter(pk=reversal.pk).update(
                consumption=-(original.consumption or Decimal('0')),
                total_cost=-(original.total_cost or Decimal('0')),
            )
    except Exception:
        pass


def _connect_eam_hooks():
    """Connect EAM hooks lazily — safer if the eam app isn't loaded yet."""
    try:
        from apps.eam.models import AssetMeterReading
    except ImportError:
        return
    post_save.connect(
        _on_meter_reading_save, sender=AssetMeterReading, weak=False,
        dispatch_uid='utility.eam_meter_reading_to_consumption',
    )
    pre_delete.connect(
        _on_meter_reading_delete, sender=AssetMeterReading, weak=False,
        dispatch_uid='utility.eam_meter_reading_to_consumption_reverse',
    )


_connect_eam_hooks()


# ----------------------------------------------------------------------------
# Cross-module hook 2 - UtilityConsumption -> CarbonEmission
# ----------------------------------------------------------------------------

def _on_consumption_save(sender, instance, created, **kwargs):
    """Auto-emit a CarbonEmission row when a consumption is recorded.

    Idempotent via partial unique constraint on (source_consumption,) enforced
    inside ``services.carbon.emit_for_consumption``. Skips silently when:
        - this isn't a fresh creation (no respawn on edit),
        - the row is itself a reversal (don't emit carbon for reversals),
        - no matching active EmissionFactor exists for the utility_type
          (handled inside the service via the _SCOPE_MAP lookup),
        - no cost.AccountingPeriod covers period_start (no period -> no
          carbon ledger row; handled inside the service).
    """
    if not created:
        return
    if instance.is_reversal:
        return
    try:
        from apps.utility.services import carbon as carbon_svc
        with transaction.atomic():
            carbon_svc.emit_for_consumption(instance)
    except Exception:
        # Auto-feed is best-effort; never break the consumption write path.
        pass


def _on_consumption_delete(sender, instance, **kwargs):
    """Reverse the matching CarbonEmission row when consumption is deleted.

    Same shape as _on_meter_reading_delete: emit a NEW reversal row instead
    of mutating or deleting the original. pre_delete (not post_delete)
    because on_delete=SET_NULL on CarbonEmission.source_consumption clears
    the FK during deletion.
    """
    original = um.CarbonEmission.all_objects.filter(
        source_consumption=instance, is_reversal=False,
    ).first()
    if original is None:
        return
    if um.CarbonEmission.all_objects.filter(
        tenant_id=original.tenant_id,
        period=original.period,
        is_reversal=True,
        notes__startswith=f'reversal-of:{original.entry_number}',
    ).exists():
        return
    try:
        with transaction.atomic():
            reversal = um.CarbonEmission.all_objects.create(
                tenant=original.tenant,
                period=original.period,
                scope=original.scope,
                source_type=original.source_type,
                source_quantity=Decimal('0'),
                factor=original.factor,
                source_consumption=None,
                source_allocation=original.source_allocation,
                recorded_at=timezone.now(),
                is_reversal=True,
                notes=f'reversal-of:{original.entry_number} (consumption deleted)',
            )
            # Override the persisted values with negated originals so the
            # reversal nets out the original in downstream rollups.
            um.CarbonEmission.all_objects.filter(pk=reversal.pk).update(
                source_quantity=-(original.source_quantity or Decimal('0')),
                co2e_kg=-(original.co2e_kg or Decimal('0')),
            )
    except Exception:
        pass


post_save.connect(
    _on_consumption_save, sender=um.UtilityConsumption, weak=False,
    dispatch_uid='utility.consumption_to_carbon',
)
pre_delete.connect(
    _on_consumption_delete, sender=um.UtilityConsumption, weak=False,
    dispatch_uid='utility.consumption_to_carbon_reverse',
)
