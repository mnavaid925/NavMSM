"""Sub-module 14.3 - peak demand management services.

Read-only recommendations: PeakShavingSuggestion rows are emitted but the
underlying pps.ScheduledOperation rows are never mutated.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone


def scan_for_peak_overlap(tenant, *, horizon_days=14):
    """Scan ScheduledOperation rows in the next horizon_days and emit
    PeakShavingSuggestion rows for any that overlap an active TOU peak band
    or active DemandResponseEvent. Idempotent.
    """
    from apps.utility import models
    from apps.pps.models import ScheduledOperation

    now = timezone.now()
    end = now + timedelta(days=horizon_days)
    ops = (
        ScheduledOperation.all_objects
        .select_related('production_order')
        .filter(
            tenant=tenant,
            scheduled_start__gte=now,
            scheduled_start__lte=end,
        )
        .order_by('scheduled_start')
    )

    # 1) Active DR events overlapping the horizon
    dr_events = list(models.DemandResponseEvent.all_objects.filter(
        tenant=tenant,
        status__in=('scheduled', 'active'),
        end_at__gte=now,
        start_at__lte=end,
    ))

    # 2) Active peak TOU bands
    peak_bands = list(models.TOURateBand.all_objects.filter(
        tariff__tenant=tenant,
        tariff__is_active=True,
        band_type='peak',
    ).select_related('tariff'))

    created = 0
    for op in ops:
        op_start = op.scheduled_start
        op_end = op.scheduled_end or op_start
        # DR event overlap
        for ev in dr_events:
            if op_end <= ev.start_at or op_start >= ev.end_at:
                continue
            existing = models.PeakShavingSuggestion.all_objects.filter(
                scheduled_operation=op, event=ev,
            ).first()
            if existing:
                continue
            sug_start = ev.end_at
            sug_end = sug_start + (op_end - op_start)
            savings = compute_estimated_savings(op, current_band=None, target_band=None)
            models.PeakShavingSuggestion.all_objects.create(
                tenant=tenant,
                event=ev,
                tou_band=None,
                production_order=op.production_order,
                scheduled_operation=op,
                original_start=op_start,
                original_end=op_end,
                suggested_start=sug_start,
                suggested_end=sug_end,
                estimated_savings=savings,
                status='new',
            )
            created += 1
        # Peak TOU band overlap
        for band in peak_bands:
            if not _band_applies_on(op_start, band):
                continue
            if not _time_overlaps(op_start, op_end, band):
                continue
            # Skip if a DR-event suggestion already exists for this op
            if models.PeakShavingSuggestion.all_objects.filter(
                scheduled_operation=op, tou_band=band,
            ).exists():
                continue
            if models.PeakShavingSuggestion.all_objects.filter(
                scheduled_operation=op, event__isnull=False,
            ).exists():
                continue
            target_band = _next_off_peak_band(band.tariff)
            sug_start = compute_suggested_slot(op_start, op_end, band, target_band)
            sug_end = sug_start + (op_end - op_start) if sug_start else None
            savings = compute_estimated_savings(op, current_band=band, target_band=target_band)
            models.PeakShavingSuggestion.all_objects.create(
                tenant=tenant,
                event=None,
                tou_band=band,
                production_order=op.production_order,
                scheduled_operation=op,
                original_start=op_start,
                original_end=op_end,
                suggested_start=sug_start,
                suggested_end=sug_end,
                estimated_savings=savings,
                status='new',
            )
            created += 1
    return {'created': created, 'horizon_days': horizon_days}


def _band_applies_on(dt, band):
    """Does ``band.day_of_week`` apply on the dt's weekday?"""
    wd = dt.weekday()  # 0 Mon ... 6 Sun
    if band.day_of_week == 'all':
        return True
    if band.day_of_week == 'weekday':
        return wd <= 4
    if band.day_of_week == 'weekend':
        return wd >= 5
    try:
        return int(band.day_of_week) == wd
    except (ValueError, TypeError):
        return False


def _time_overlaps(op_start, op_end, band):
    """Check whether the op's time window crosses the band's time window."""
    op_start_t = op_start.time()
    op_end_t = op_end.time() if op_end.date() == op_start.date() else time(23, 59, 59)
    # Standard overlap: a < d and c < b (where a,b is band; c,d is op)
    return op_start_t < band.end_time and band.start_time < op_end_t


def _next_off_peak_band(tariff):
    """Find the first off_peak band on the same tariff (best-effort)."""
    from apps.utility import models
    return (
        models.TOURateBand.all_objects
        .filter(tariff=tariff, band_type='off_peak')
        .order_by('start_time').first()
    )


def compute_suggested_slot(op_start, op_end, current_band, target_band):
    """Pure: compute a suggested off-peak slot of the same duration.

    v1: shift the op to the start of the next off_peak band on the same day,
    or the next day if the off_peak window has already passed.
    """
    if target_band is None:
        return None
    candidate = datetime.combine(op_start.date(), target_band.start_time, tzinfo=op_start.tzinfo)
    if candidate <= op_start:
        candidate = candidate + timedelta(days=1)
    return candidate


def compute_estimated_savings(op, *, current_band=None, target_band=None):
    """Pure: rough estimate of $ saved by shifting the op out of peak.

    v1 heuristic: op duration in hours x assumed avg load of 50 kWh/hr x rate diff.
    The model holds asset/cost-center linkage so a future revision can pull
    the actual avg_kwh_per_hour from EAM telemetry.
    """
    op_start = op.scheduled_start
    op_end = op.scheduled_end or op_start
    duration_hours = Decimal((op_end - op_start).total_seconds()) / Decimal('3600')
    assumed_kwh_per_hour = Decimal('50')
    if current_band is None or target_band is None:
        return (duration_hours * assumed_kwh_per_hour * Decimal('0.06')).quantize(Decimal('0.01'))
    rate_diff = (current_band.rate or Decimal('0')) - (target_band.rate or Decimal('0'))
    if rate_diff < 0:
        rate_diff = Decimal('0')
    return (duration_hours * assumed_kwh_per_hour * rate_diff).quantize(Decimal('0.01'))


@transaction.atomic
def acknowledge(suggestion, *, by=None):
    if suggestion.status != 'new':
        return suggestion
    suggestion.status = 'acknowledged'
    suggestion.acknowledged_by = by
    suggestion.acknowledged_at = timezone.now()
    suggestion.save(update_fields=['status', 'acknowledged_by', 'acknowledged_at'])
    return suggestion


@transaction.atomic
def dismiss(suggestion, *, reason, by=None):
    if suggestion.status == 'dismissed':
        return suggestion
    suggestion.status = 'dismissed'
    suggestion.dismiss_reason = reason
    suggestion.acknowledged_by = by
    suggestion.acknowledged_at = timezone.now()
    suggestion.save(update_fields=['status', 'dismiss_reason', 'acknowledged_by', 'acknowledged_at'])
    return suggestion
