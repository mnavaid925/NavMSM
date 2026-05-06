"""Pure-function helpers for labor cost allocation.

The signals.py / view layer is responsible for the ORM hits. These helpers
encapsulate the math so it can be unit-tested without a database.
"""
from datetime import date as DateType, datetime
from decimal import Decimal


def compute_total_cost(minutes: int, hourly_rate: Decimal) -> Decimal:
    """Return total cost = minutes * hourly_rate / 60, quantized to 2dp."""
    if minutes <= 0 or hourly_rate is None or hourly_rate <= 0:
        return Decimal('0.00')
    return (Decimal(int(minutes)) * Decimal(hourly_rate) / Decimal('60')).quantize(Decimal('0.01'))


def lookup_effective_rate(rates, at_dt) -> Decimal:
    """Return the LaborRate effective at ``at_dt`` from an iterable of rate-rows.

    A rate-row is anything with ``effective_from``, ``effective_to`` (nullable),
    and ``hourly_rate`` attributes - typically a queryset row but works on
    any duck-typed list.
    """
    if at_dt is None:
        return Decimal('0')
    at_date = at_dt.date() if isinstance(at_dt, datetime) else at_dt
    candidates = [
        r for r in rates
        if r.effective_from <= at_date
        and (r.effective_to is None or r.effective_to >= at_date)
    ]
    if not candidates:
        return Decimal('0')
    candidates.sort(key=lambda r: r.effective_from, reverse=True)
    return Decimal(candidates[0].hourly_rate)


def summarize_by_cost_center(bookings):
    """Aggregate an iterable of LaborBooking-like rows into per-cost-center totals.

    Returns a dict keyed by ``cost_center_id`` (None included) -> dict with
    keys ``minutes`` (int) and ``total_cost`` (Decimal).
    """
    out: dict = {}
    for b in bookings:
        key = b.cost_center_id
        bucket = out.setdefault(key, {'minutes': 0, 'total_cost': Decimal('0.00')})
        bucket['minutes'] += int(b.minutes or 0)
        bucket['total_cost'] += Decimal(b.total_cost or 0)
    return out
