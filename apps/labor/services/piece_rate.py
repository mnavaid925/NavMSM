"""Pure-function helpers for piece-rate / incentive calculations.

The signals + view layers handle the ORM. These helpers compute amounts.
"""
from decimal import Decimal


def compute_amount(units: Decimal | int | float, rate: Decimal | int | float) -> Decimal:
    """Return units * rate, quantized to 2 decimal places. Floors at 0."""
    if units is None or rate is None:
        return Decimal('0.00')
    u = Decimal(str(units))
    r = Decimal(str(rate))
    if u <= 0 or r <= 0:
        return Decimal('0.00')
    return (u * r).quantize(Decimal('0.01'))


def select_rate(piece_rates, *, product=None, operation=None, qty: Decimal = Decimal('0')):
    """Pick the matching PieceRate row.

    Preference: operation match > product match > both NULL (catch-all).
    Filters by min_quantity / max_quantity bands when set.
    Returns None if no row matches.
    """
    qty = Decimal(qty or 0)
    candidates = []
    for r in piece_rates:
        if r.min_quantity is not None and qty < Decimal(r.min_quantity):
            continue
        if r.max_quantity is not None and qty > Decimal(r.max_quantity):
            continue
        if operation and r.operation_id == getattr(operation, 'pk', operation):
            candidates.append((0, r))
        elif product and r.product_id == getattr(product, 'pk', product):
            candidates.append((1, r))
        elif r.product_id is None and r.operation_id is None:
            candidates.append((2, r))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[0][1]


def aggregate_employee_units(reports):
    """Return a dict ``{employee_id: total_good_qty}`` from an iterable of reports."""
    out: dict = {}
    for r in reports:
        emp_id = getattr(r, 'reported_by_id', None)
        if emp_id is None:
            continue
        out[emp_id] = out.get(emp_id, Decimal('0')) + Decimal(r.good_qty or 0)
    return out
