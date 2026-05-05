"""Pure-function PM schedule generator.

Given a MaintenancePlan and a horizon (in days), compute the next-due dates
that should be materialised as PMSchedule rows. The function is ORM-agnostic
beyond reading the input plan - the caller is responsible for filtering out
already-existing schedules and persisting the new ones.

Trigger types:
    - 'calendar': next_due = (last_done_at or today) + frequency_days
    - 'meter':    next_due = NULL date (consumed when meter reaches threshold)
    - 'both':     emit calendar-driven entries; meter cap-checks are caller-side.

The function returns a list of (scheduled_date, scheduled_meter) tuples ready
to feed into PMSchedule(...).
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple


@dataclass
class PlanLike:
    """Shape this service needs from a MaintenancePlan (duck-typed)."""

    trigger_type: str
    frequency_days: Optional[int]
    frequency_meter: Optional[Decimal]
    last_done_at: Optional[date]
    last_done_meter: Optional[Decimal]
    next_due_at: Optional[date]
    next_due_meter: Optional[Decimal]


def generate_upcoming_pm(
    plan,
    horizon_days: int = 90,
    today: Optional[date] = None,
    max_count: int = 6,
) -> List[Tuple[Optional[date], Optional[Decimal]]]:
    """Return up to `max_count` (scheduled_date, scheduled_meter) tuples.

    Calendar / both triggers fan out future dates by `frequency_days` until
    `horizon_days` is exhausted (or `max_count` reached). Meter-only triggers
    return a single tuple (None, threshold) representing the next meter value
    at which the plan should fire.
    """
    today = today or date.today()
    if not getattr(plan, 'is_active', True):
        return []

    out: List[Tuple[Optional[date], Optional[Decimal]]] = []
    horizon_end = today + timedelta(days=horizon_days)

    # Calendar-driven entries.
    if plan.trigger_type in ('calendar', 'both') and plan.frequency_days:
        anchor = plan.next_due_at or _calendar_seed(plan, today)
        cursor = anchor
        # If anchor is already in the past (e.g. plan never run), pull it forward.
        while cursor < today:
            cursor += timedelta(days=plan.frequency_days)
        while cursor <= horizon_end and len(out) < max_count:
            out.append((cursor, None))
            cursor += timedelta(days=plan.frequency_days)

    # Meter-only entries: emit a single forward-looking threshold.
    if plan.trigger_type == 'meter' and plan.frequency_meter:
        threshold = (plan.last_done_meter or Decimal('0')) + Decimal(plan.frequency_meter)
        out.append((None, threshold))

    return out


def _calendar_seed(plan, today: date) -> date:
    """First-run anchor for calendar plans without a prior next_due_at."""
    if plan.last_done_at and plan.frequency_days:
        return plan.last_done_at + timedelta(days=plan.frequency_days)
    return today
