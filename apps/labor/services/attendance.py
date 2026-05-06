"""Pure-function helpers for attendance computations.

No ORM imports at module level - the calling view/signal passes data in.
"""
from datetime import date, datetime, time, timedelta


def compute_worked_minutes(clock_in: datetime | None, clock_out: datetime | None,
                           break_minutes: int = 0) -> int:
    """Return whole minutes worked, after deducting break_minutes.

    Returns 0 when either timestamp is missing or end<=start.
    """
    if not clock_in or not clock_out:
        return 0
    if clock_out <= clock_in:
        return 0
    raw_minutes = int((clock_out - clock_in).total_seconds() // 60)
    return max(0, raw_minutes - max(0, int(break_minutes)))


def derive_status(worked_minutes: int, shift_minutes: int,
                  expected_start: time | None = None,
                  actual_start: time | None = None,
                  *,
                  late_grace_minutes: int = 10,
                  half_day_threshold_pct: int = 50) -> str:
    """Derive `present / late / half_day / absent` from worked + shift duration.

    `expected_start` and `actual_start` are compared on local time only.
    """
    if worked_minutes <= 0:
        return 'absent'
    if shift_minutes <= 0:
        return 'present' if worked_minutes > 0 else 'absent'
    pct = (worked_minutes / shift_minutes) * 100
    if pct < half_day_threshold_pct:
        return 'half_day'
    if expected_start and actual_start:
        late = (
            (datetime.combine(date.min, actual_start) -
             datetime.combine(date.min, expected_start))
            .total_seconds() // 60
        )
        if late > late_grace_minutes:
            return 'late'
    return 'present'


def shift_duration_minutes(start: time, end: time, is_overnight: bool = False) -> int:
    """Return shift length in minutes, accounting for overnight shifts."""
    base = datetime.combine(date.today(), start)
    target = datetime.combine(date.today(), end)
    if is_overnight or target <= base:
        target += timedelta(days=1)
    return int((target - base).total_seconds() // 60)
