"""Overhead allocation services.

apply_overhead(period) is the orchestrator: scans DriverActuals, multiplies
by the period's pool rate, materializes ``OverheadAllocation`` rows, and
auto-emits matching ``WIPEntry(overhead_applied)`` for production-order
targets.

Idempotent: re-running clears prior allocations for the period and re-emits.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from . import wip as wip_svc


def compute_rate(budgeted_amount, budgeted_driver_qty):
    """Pure: return rate per driver unit (0 when qty is 0)."""
    if not budgeted_driver_qty or budgeted_driver_qty <= 0:
        return Decimal('0')
    return (Decimal(budgeted_amount) / Decimal(budgeted_driver_qty)).quantize(
        Decimal('0.000001')
    )


def apply_overhead(period, *, posted_by=None):
    """Materialize overhead allocations for ``period``.

    Returns dict ``{'allocations': N, 'wip_entries': M}``.
    """
    from .. import models as cm

    if period.status == 'closed':
        raise ValueError('cannot apply overhead on a closed period')

    counts = {'allocations': 0, 'wip_entries': 0}

    with transaction.atomic():
        # Wipe prior allocations + their WIP entries for the period (idempotent rerun).
        prior = cm.OverheadAllocation.all_objects.filter(
            tenant_id=period.tenant_id, period=period, is_reversed=False,
        )
        cm.WIPEntry.all_objects.filter(
            source_overhead_allocation__in=prior,
        ).delete()
        prior.delete()

        rates_by_pool = {
            r.pool_id: r for r in cm.OverheadRate.all_objects.filter(
                tenant_id=period.tenant_id, period=period, is_active=True,
            ).select_related('pool', 'driver')
        }

        for pool_id, rate in rates_by_pool.items():
            actuals = cm.DriverActuals.all_objects.filter(
                tenant_id=period.tenant_id, period=period, driver=rate.driver,
            )
            for actual in actuals:
                applied = (Decimal(actual.quantity) * rate.rate_per_driver_unit).quantize(
                    Decimal('0.01')
                )
                allocation = cm.OverheadAllocation.all_objects.create(
                    tenant_id=period.tenant_id,
                    pool=rate.pool,
                    period=period,
                    target_cost_center=actual.cost_center,
                    target_production_order=actual.production_order,
                    driver_qty=actual.quantity,
                    rate_applied=rate.rate_per_driver_unit,
                    applied_amount=applied,
                    posted_by=posted_by,
                )
                counts['allocations'] += 1

                # Auto-emit WIPEntry for production-order targets.
                if actual.production_order_id is not None:
                    job = cm.JobCost.all_objects.filter(
                        production_order_id=actual.production_order_id,
                    ).first()
                    if job is not None and applied > 0:
                        wip_svc.post_wip_entry(
                            tenant=period.tenant,
                            job=job,
                            entry_type='overhead_applied',
                            amount=applied,
                            cost_center=actual.cost_center,
                            source_overhead_allocation=allocation,
                            posted_by=posted_by,
                        )
                        counts['wip_entries'] += 1
    return counts


def reverse_overhead(period, *, posted_by=None, reason=''):
    """Mark all active allocations for the period as reversed and emit
    offsetting WIPEntry rows.

    Refuses on closed periods.
    """
    from .. import models as cm

    if period.status == 'closed':
        raise ValueError('cannot reverse overhead on a closed period')

    counts = {'reversed': 0, 'wip_offsets': 0}
    qs = cm.OverheadAllocation.all_objects.filter(
        tenant_id=period.tenant_id, period=period, is_reversed=False,
    )
    with transaction.atomic():
        for alloc in qs:
            wip = cm.WIPEntry.all_objects.filter(
                source_overhead_allocation=alloc, is_reversal=False,
            ).first()
            if wip is not None:
                wip_svc.reverse_wip_entry(wip, posted_by=posted_by, reason=reason)
                counts['wip_offsets'] += 1
            alloc.is_reversed = True
            alloc.reversal_reason = reason
            alloc.save(update_fields=['is_reversed', 'reversal_reason', 'updated_at'])
            counts['reversed'] += 1
    return counts


def accumulate_indirect_labor(period, pool, amount):
    """Bump the OverheadActualPool for the period+pool by ``amount``.

    Used by labor.LaborBooking(kind='indirect') signal hook.
    Idempotent (additive).
    """
    from .. import models as cm

    amount = Decimal(amount)
    with transaction.atomic():
        actual, _ = cm.OverheadActualPool.all_objects.get_or_create(
            tenant_id=period.tenant_id,
            pool=pool, period=period,
            defaults={'actual_amount': Decimal('0')},
        )
        actual.actual_amount = (actual.actual_amount or Decimal('0')) + amount
        actual.save()
    return actual
