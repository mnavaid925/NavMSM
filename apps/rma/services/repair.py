"""Repair-order cost roll-up service for Module 18 - Returns & RMA.

`recompute_repair_costs` aggregates the append-only RepairPartUsage +
RepairLaborLog ledgers onto the parent RepairOrder's denorm fields. It
is the single writer of `RepairOrder.actual_cost` / `labor_minutes` so
the denorms never drift - signals and views both call through here.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum


def recompute_repair_costs(repair_order) -> None:
    """Refresh `actual_cost` + `labor_minutes` denorms from child ledgers.

    parts_cost = sum(quantity * unit_cost) over RepairPartUsage
    labor_cost = sum(labor_cost) over RepairLaborLog
    labor_minutes = sum(minutes) over RepairLaborLog
    actual_cost = parts_cost + labor_cost
    """
    parts = repair_order.part_usages.aggregate(
        total=Sum('line_cost'),
    )['total'] or Decimal('0')
    labor = repair_order.labor_logs.aggregate(
        cost=Sum('labor_cost'), minutes=Sum('minutes'),
    )
    labor_cost = labor['cost'] or Decimal('0')
    labor_minutes = labor['minutes'] or 0

    repair_order.actual_cost = (parts + labor_cost).quantize(Decimal('0.01'))
    repair_order.labor_minutes = labor_minutes
    repair_order.save(update_fields=['actual_cost', 'labor_minutes', 'updated_at'])
