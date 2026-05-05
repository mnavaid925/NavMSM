"""Pure-function downtime aggregator.

Given an iterable of DowntimeEvent rows (or duck-typed objects), compute total
downtime minutes and split planned / unplanned. Used by the MWO denorm refresh
and the asset KPI dashboard.
"""
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class DowntimeSummary:
    total_minutes: Decimal
    planned_minutes: Decimal
    unplanned_minutes: Decimal
    event_count: int

    @property
    def unplanned_pct(self) -> Decimal:
        if not self.total_minutes:
            return Decimal('0')
        return (self.unplanned_minutes * Decimal('100') / self.total_minutes).quantize(Decimal('0.01'))


def compute_downtime(events) -> DowntimeSummary:
    """Sum and bucket a sequence of DowntimeEvent-like rows."""
    total = planned = unplanned = Decimal('0')
    count = 0
    for ev in events:
        m = Decimal(getattr(ev, 'minutes', 0) or 0)
        total += m
        if getattr(ev, 'downtime_type', 'unplanned') == 'planned':
            planned += m
        else:
            unplanned += m
        count += 1
    return DowntimeSummary(
        total_minutes=total.quantize(Decimal('0.01')),
        planned_minutes=planned.quantize(Decimal('0.01')),
        unplanned_minutes=unplanned.quantize(Decimal('0.01')),
        event_count=count,
    )


def refresh_mwo_downtime(mwo) -> Decimal:
    """Recompute and persist `MaintenanceWorkOrder.downtime_minutes`.

    Uses .update() so the row is touched once; returns the new total.
    """
    from apps.eam.models import MaintenanceWorkOrder
    summary = compute_downtime(mwo.downtime_events.all())
    MaintenanceWorkOrder.all_objects.filter(pk=mwo.pk).update(
        downtime_minutes=summary.total_minutes,
    )
    return summary.total_minutes
