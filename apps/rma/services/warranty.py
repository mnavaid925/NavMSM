"""Pure-function warranty helpers for Module 18 - Returns & RMA.

No ORM imports at module scope - these are deterministic date / status
calculators consumed by `WarrantyPolicy`, `WarrantyRegistration.save()`
and the `expire_warranties` management command.
"""
from __future__ import annotations

import calendar
from datetime import date


def add_months(start: date, months: int) -> date:
    """Return `start` shifted forward by `months` calendar months.

    Day-of-month is clamped to the last valid day of the target month
    (so 31 Jan + 1 month -> 28/29 Feb). `dateutil` is intentionally NOT
    used - it is not a project dependency.
    """
    if start is None:
        return None
    months = int(months or 0)
    zero_based = start.month - 1 + months
    year = start.year + zero_based // 12
    month = zero_based % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def compute_warranty_end(start: date, duration_months: int) -> date:
    """End date of a warranty that runs `duration_months` from `start`."""
    return add_months(start, duration_months)


def is_under_warranty(start: date, end: date, on_date: date | None = None) -> bool:
    """True when `on_date` (default today) falls within [start, end]."""
    if start is None or end is None:
        return False
    on_date = on_date or date.today()
    return start <= on_date <= end
