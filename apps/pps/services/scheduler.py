"""Scheduling primitives — pure functions, no ORM imports at module level.

The scheduler walks an iterable of routing operations and lays them onto a
work-center calendar. The output is a list of dicts; the caller is
responsible for persisting `ScheduledOperation` rows. Keeping the algorithm
side-effect-free keeps it unit-testable and reusable from the simulator.

Calendar model: each work center carries a list of `(day_of_week,
shift_start, shift_end, is_working)` tuples. The scheduler advances a
cursor through this calendar, consuming minutes for setup + run + queue +
move on each operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Iterable


def _strip_tz(dt: datetime) -> tuple[datetime, object]:
    """Return (naive datetime, tzinfo) so the caller can re-attach tz on output."""
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None), dt.tzinfo
    return dt, None


def _attach_tz(dt: datetime, tz):
    return dt.replace(tzinfo=tz) if tz is not None else dt


@dataclass
class OperationRequest:
    """A unit of work the scheduler must place on a calendar."""

    sequence: int
    operation_name: str
    work_center_id: int
    work_center_code: str
    setup_minutes: Decimal
    run_minutes_per_unit: Decimal
    queue_minutes: Decimal
    move_minutes: Decimal

    def total_minutes(self, quantity: Decimal) -> int:
        run = self.run_minutes_per_unit * Decimal(str(quantity))
        total = self.setup_minutes + run + self.queue_minutes + self.move_minutes
        return int(total.quantize(Decimal('1')))


@dataclass
class ScheduledSlot:
    """Output unit — one operation placed on the calendar."""

    sequence: int
    operation_name: str
    work_center_id: int
    work_center_code: str
    planned_start: datetime
    planned_end: datetime
    planned_minutes: int


def _shifts_for_date(calendar: dict[int, list[tuple[time, time, bool]]],
                     d: date) -> list[tuple[time, time]]:
    """Return ordered list of working (shift_start, shift_end) tuples for a date."""
    shifts = calendar.get(d.weekday(), [])
    return [(s, e) for s, e, working in shifts if working]


def _advance_to_next_window(cursor: datetime,
                            calendar: dict[int, list[tuple[time, time, bool]]]) -> datetime:
    """Push the cursor forward to the start of the next working shift on or after cursor."""
    horizon_days = 30  # safety net — most schedules won't push past a month
    for _ in range(horizon_days):
        d = cursor.date()
        shifts = _shifts_for_date(calendar, d)
        for s, e in shifts:
            shift_start = datetime.combine(d, s)
            shift_end = datetime.combine(d, e)
            if cursor < shift_end:
                return max(cursor, shift_start)
        cursor = datetime.combine(d + timedelta(days=1), time(0, 0))
    return cursor


def _consume_minutes(cursor: datetime,
                     minutes: int,
                     calendar: dict[int, list[tuple[time, time, bool]]]) -> tuple[datetime, datetime]:
    """Consume `minutes` of working time starting at cursor, walking forward across shifts."""
    cursor = _advance_to_next_window(cursor, calendar)
    start = cursor
    remaining = minutes
    horizon_days = 60
    for _ in range(horizon_days):
        d = cursor.date()
        for s, e in _shifts_for_date(calendar, d):
            shift_start = datetime.combine(d, s)
            shift_end = datetime.combine(d, e)
            if cursor >= shift_end:
                continue
            avail_in_shift = int((shift_end - max(cursor, shift_start)).total_seconds() // 60)
            if avail_in_shift <= 0:
                continue
            if remaining <= avail_in_shift:
                end = max(cursor, shift_start) + timedelta(minutes=remaining)
                return start, end
            remaining -= avail_in_shift
            cursor = shift_end
        cursor = datetime.combine(d + timedelta(days=1), time(0, 0))
    # Capacity blew past the safety horizon; fall back to wall-clock end.
    return start, start + timedelta(minutes=minutes)


def schedule_forward(operations: Iterable[OperationRequest],
                     *,
                     start: datetime,
                     quantity: Decimal,
                     calendars: dict[int, dict[int, list[tuple[time, time, bool]]]],
                     ) -> list[ScheduledSlot]:
    """Place each operation onto its work center's calendar starting at `start`.

    `calendars` is a mapping of work_center_id -> {day_of_week: [(shift_start,
    shift_end, is_working), ...]}.
    """
    naive_start, tz = _strip_tz(start)
    cursor_per_wc: dict[int, datetime] = {}
    slots: list[ScheduledSlot] = []
    flow_cursor = naive_start
    for op in operations:
        cal = calendars.get(op.work_center_id, {})
        wc_cursor = cursor_per_wc.get(op.work_center_id, naive_start)
        # Operation can only start once the previous op finishes (flow_cursor)
        # AND once the work center is free (wc_cursor).
        cursor = max(flow_cursor, wc_cursor)
        minutes = op.total_minutes(quantity)
        actual_start, actual_end = _consume_minutes(cursor, minutes, cal)
        slots.append(ScheduledSlot(
            sequence=op.sequence,
            operation_name=op.operation_name,
            work_center_id=op.work_center_id,
            work_center_code=op.work_center_code,
            planned_start=_attach_tz(actual_start, tz),
            planned_end=_attach_tz(actual_end, tz),
            planned_minutes=minutes,
        ))
        cursor_per_wc[op.work_center_id] = actual_end
        flow_cursor = actual_end
    return slots


def schedule_backward(operations: list[OperationRequest],
                      *,
                      end: datetime,
                      quantity: Decimal,
                      calendars: dict[int, dict[int, list[tuple[time, time, bool]]]],
                      ) -> list[ScheduledSlot]:
    """Backward scheduling — last operation finishes at `end`; earlier ones precede it.

    Implementation note: we run forward scheduling from a probe start that's
    `total_minutes / capacity_density` before `end`, then shift the entire
    block so its last operation ends exactly at `end`. This preserves the
    forward-walking calendar logic without needing a separate reverse walk.
    """
    if not operations:
        return []
    quantity_dec = Decimal(str(quantity))
    total = sum(op.total_minutes(quantity_dec) for op in operations)
    # Probe start: a generous buffer (3x) to absorb shift breaks.
    probe = end - timedelta(minutes=total * 3)
    forward = schedule_forward(operations, start=probe, quantity=quantity_dec, calendars=calendars)
    if not forward:
        return forward
    drift = forward[-1].planned_end - end
    # Slide everything backward so the final op ends at `end`.
    return [
        ScheduledSlot(
            sequence=s.sequence,
            operation_name=s.operation_name,
            work_center_id=s.work_center_id,
            work_center_code=s.work_center_code,
            planned_start=s.planned_start - drift,
            planned_end=s.planned_end - drift,
            planned_minutes=s.planned_minutes,
        )
        for s in forward
    ]


def schedule_infinite(operations: Iterable[OperationRequest],
                      *,
                      start: datetime,
                      quantity: Decimal) -> list[ScheduledSlot]:
    """Capacity-blind scheduling: lay operations end-to-end on wall-clock time."""
    naive_cursor, tz = _strip_tz(start)
    cursor = naive_cursor
    slots: list[ScheduledSlot] = []
    quantity_dec = Decimal(str(quantity))
    for op in operations:
        minutes = op.total_minutes(quantity_dec)
        end = cursor + timedelta(minutes=minutes)
        slots.append(ScheduledSlot(
            sequence=op.sequence,
            operation_name=op.operation_name,
            work_center_id=op.work_center_id,
            work_center_code=op.work_center_code,
            planned_start=_attach_tz(cursor, tz),
            planned_end=_attach_tz(end, tz),
            planned_minutes=minutes,
        ))
        cursor = end
    return slots


def compute_load(scheduled_minutes_per_day: dict[date, int],
                 available_minutes_per_day: dict[date, int],
                 *,
                 bottleneck_threshold: Decimal = Decimal('95')) -> dict[date, dict]:
    """Return per-day load summary suitable for persisting to CapacityLoad.

    For each date in `scheduled_minutes_per_day` (or `available_minutes_per_day`,
    whichever is wider), produces a dict: planned, available, utilization_pct,
    is_bottleneck. Days with no working calendar (available=0) are reported
    only if planned > 0.
    """
    result: dict[date, dict] = {}
    all_dates = set(scheduled_minutes_per_day) | set(available_minutes_per_day)
    for d in sorted(all_dates):
        planned = scheduled_minutes_per_day.get(d, 0)
        available = available_minutes_per_day.get(d, 0)
        if available <= 0:
            util = Decimal('0') if planned == 0 else Decimal('999')
        else:
            util = (Decimal(str(planned)) / Decimal(str(available)) * Decimal('100')
                    ).quantize(Decimal('0.01'))
        result[d] = {
            'planned_minutes': planned,
            'available_minutes': available,
            'utilization_pct': util,
            'is_bottleneck': util >= bottleneck_threshold,
        }
    return result
