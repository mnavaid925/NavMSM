"""Sub-module 14.2 - utility cost allocation services.

The post_allocation orchestrator emits matching cost.DriverActuals rows so
the existing cost.services.overhead.apply_overhead(period) sweeps the
utility cost into the Utilities pool automatically.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.utility import models


def compute_allocation(period, meter, targets):
    """Pure: return per-target allocation share dict.

    ``targets`` is an iterable of dicts of the form::

        {'cost_center': cc | None, 'product': p | None,
         'production_order': po | None, 'share_pct': Decimal}

    The function does NOT touch the DB; callers persist via post_allocation.
    Total share is normalized to <= 100% (form layer enforces this).
    """
    total_consumption, total_cost = _aggregate_meter_for_period(period, meter)
    out = []
    for t in targets:
        share = (t.get('share_pct') or Decimal('0')) / Decimal('100')
        out.append({
            'cost_center': t.get('cost_center'),
            'product': t.get('product'),
            'production_order': t.get('production_order'),
            'share_pct': t.get('share_pct') or Decimal('0'),
            'allocated_consumption': (total_consumption * share).quantize(Decimal('0.0001')),
            'allocated_cost': (total_cost * share).quantize(Decimal('0.01')),
        })
    return out


def _aggregate_meter_for_period(period, meter):
    qs = models.UtilityConsumption.all_objects.filter(
        tenant=meter.tenant, meter=meter,
        period_start__date__gte=period.start_date,
        period_end__date__lte=period.end_date,
        is_reversal=False,
    )
    agg = qs.aggregate(c=Sum('consumption'), t=Sum('total_cost'))
    return (agg.get('c') or Decimal('0')), (agg.get('t') or Decimal('0'))


@transaction.atomic
def post_allocation(period, meter, targets, posted_by=None):
    """Idempotent orchestrator.

    For each target row:
        - Wipes prior UtilityAllocation + matching cost.DriverActuals.
        - Writes a new UtilityAllocation row.
        - If the target is a cost_center or production_order, writes a
          matching cost.DriverActuals row so cost.apply_overhead() sweeps
          it into the Utilities pool automatically.
    """
    from apps.cost.models import DriverActuals
    # Idempotency: clear prior allocations + matching driver_actuals for this
    # (period, meter, tenant) tuple before re-emitting.
    prior = models.UtilityAllocation.all_objects.filter(
        tenant=meter.tenant, period=period, meter=meter, is_reversed=False,
    )
    prior_ids = list(prior.values_list('id', flat=True))
    if meter.utility_type.cost_driver_id:
        DriverActuals.all_objects.filter(
            tenant=meter.tenant,
            driver=meter.utility_type.cost_driver,
            period=period,
            notes__startswith=f'utility:{meter.meter_number}:',
        ).delete()
    prior.delete()

    rows = compute_allocation(period, meter, targets)
    created = []
    cost_driver = meter.utility_type.cost_driver
    for r in rows:
        alloc = models.UtilityAllocation.all_objects.create(
            tenant=meter.tenant,
            period=period,
            meter=meter,
            target_cost_center=r['cost_center'],
            target_product=r['product'],
            target_production_order=r['production_order'],
            allocation_method='meter_consumption',
            share_pct=r['share_pct'],
            allocated_consumption=r['allocated_consumption'],
            allocated_cost=r['allocated_cost'],
            is_posted_to_cost=False,
            posted_by=posted_by,
        )
        # Bridge into cost: write a DriverActuals row so apply_overhead picks it up.
        if cost_driver and (r['cost_center'] or r['production_order']):
            DriverActuals.all_objects.create(
                tenant=meter.tenant,
                driver=cost_driver,
                period=period,
                cost_center=r['cost_center'],
                production_order=r['production_order'],
                quantity=r['allocated_consumption'],
                recorded_by=posted_by,
                recorded_at=timezone.now(),
                notes=f'utility:{meter.meter_number}:{alloc.allocation_number}',
            )
            alloc.is_posted_to_cost = True
            alloc.posted_at = timezone.now()
            alloc.save(update_fields=['is_posted_to_cost', 'posted_at'])
        created.append(alloc)
    return {'created': len(created), 'cleared_prior': len(prior_ids)}


@transaction.atomic
def reverse_allocation(allocation, *, reason, reversed_by=None):
    """Mark allocation reversed and remove the matching DriverActuals row."""
    from apps.cost.models import DriverActuals
    if allocation.is_reversed:
        return allocation
    if allocation.meter.utility_type.cost_driver_id:
        DriverActuals.all_objects.filter(
            tenant=allocation.tenant,
            driver=allocation.meter.utility_type.cost_driver,
            period=allocation.period,
            notes=f'utility:{allocation.meter.meter_number}:{allocation.allocation_number}',
        ).delete()
    allocation.is_reversed = True
    allocation.reversal_reason = reason
    allocation.save(update_fields=['is_reversed', 'reversal_reason'])
    return allocation
