"""Capable-to-Promise (CTP) service - 17.3.

When ATP shows a shortfall, walk the BOM + Routing capacity to estimate
the earliest realistic completion date for the shortfall qty. Heuristic
only - never writes; never alters the PPS schedule.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class CTPResult:
    shortfall_qty: Decimal
    target_date: date
    capable_qty: Decimal
    earliest_completion_date: Optional[date]
    bottleneck_work_center_id: Optional[int]
    trace: dict = field(default_factory=dict)


def _released_bom_for(tenant, product):
    try:
        from apps.bom.models import BillOfMaterials
        return BillOfMaterials.all_objects.filter(
            tenant=tenant, product=product, status='released',
        ).order_by('-id').first()
    except Exception:
        return None


def _default_routing_for(tenant, product):
    try:
        from apps.pps.models import Routing
        return Routing.all_objects.filter(
            tenant=tenant, product=product, status='released',
        ).order_by('-id').first()
    except Exception:
        return None


def _capacity_minutes_per_day(work_center) -> Decimal:
    """Return a rough daily capacity figure (minutes) for the work center."""
    capacity = getattr(work_center, 'capacity_minutes_per_day', None)
    if capacity is not None:
        return Decimal(capacity)
    # Fallback: 1 shift * 8 hours = 480 min
    return Decimal('480')


def compute_ctp(
    tenant,
    product,
    shortfall_qty,
    target_date: date,
) -> CTPResult:
    """Compute earliest_completion_date for `shortfall_qty` units of `product`.

    Algorithm (heuristic):
        1. Walk released routing for the product.
        2. For each operation, compute total required minutes
           = cycle_seconds * qty / 60 + setup_minutes.
        3. Total elapsed days = sum( minutes / per-day-capacity ) for each
           op's work center.
        4. Earliest completion date = today + elapsed_days (rounded up to days).
        5. Bottleneck = work center with highest required minutes.
    """
    shortfall_qty = Decimal(shortfall_qty)
    today = date.today()

    routing = _default_routing_for(tenant, product)
    trace = {
        'product_id': product.id,
        'shortfall_qty': str(shortfall_qty),
        'target_date': str(target_date),
        'operations': [],
    }

    if routing is None:
        return CTPResult(
            shortfall_qty=shortfall_qty,
            target_date=target_date,
            capable_qty=Decimal('0'),
            earliest_completion_date=None,
            bottleneck_work_center_id=None,
            trace={**trace, 'reason': 'no released routing for product'},
        )

    total_days = Decimal('0')
    max_minutes = Decimal('0')
    bottleneck_wc = None

    try:
        operations = routing.operations.all().order_by('sequence')
    except Exception:
        operations = []

    for op in operations:
        cycle = Decimal(getattr(op, 'cycle_seconds', 0) or 0)
        setup = Decimal(getattr(op, 'setup_minutes', 0) or 0)
        required_minutes = (cycle * shortfall_qty / Decimal('60')) + setup
        wc = getattr(op, 'work_center', None)
        per_day = _capacity_minutes_per_day(wc) if wc else Decimal('480')
        op_days = required_minutes / per_day if per_day else Decimal('1')
        total_days += op_days
        if required_minutes > max_minutes:
            max_minutes = required_minutes
            bottleneck_wc = wc
        trace['operations'].append({
            'op_sequence': getattr(op, 'sequence', None),
            'work_center': getattr(wc, 'code', None),
            'required_minutes': str(required_minutes),
            'per_day_capacity_min': str(per_day),
            'op_days': str(op_days),
        })

    # round up to integer days
    elapsed_days = int(total_days) + (1 if total_days % 1 else 0)
    completion = today + timedelta(days=elapsed_days)

    return CTPResult(
        shortfall_qty=shortfall_qty,
        target_date=target_date,
        capable_qty=shortfall_qty,        # heuristic: assume we can always make it
        earliest_completion_date=completion,
        bottleneck_work_center_id=getattr(bottleneck_wc, 'id', None),
        trace={**trace, 'elapsed_days': elapsed_days},
    )
