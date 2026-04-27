"""Pure-function lot-sizing rules.

Each function takes a list of per-period net requirements and returns a list
of (period_index, planned_qty, planned_release_date_offset) tuples.

Methods:
    apply_l4l(net_requirements)            — order each period's net as-is
    apply_foq(net_requirements, fixed_qty) — order multiples of fixed_qty
    apply_poq(net_requirements, periods)   — group N periods into one order
    apply_min_max(net_requirements, min_qty, max_qty)
                                            — stay within [min, max]
"""
from decimal import Decimal


def _to_decimal_list(values):
    return [Decimal(str(v)) for v in values]


def apply_l4l(net_requirements):
    """Lot-for-Lot — order exactly each period's net requirement.

    Returns: list[(period_index, planned_qty)] for periods with net > 0.
    """
    nets = _to_decimal_list(net_requirements)
    return [(i, n) for i, n in enumerate(nets) if n > 0]


def apply_foq(net_requirements, fixed_qty):
    """Fixed Order Quantity — order multiples of ``fixed_qty`` to cover net.

    If a period's net <= ``fixed_qty``, plan exactly ``fixed_qty``.
    If it's larger, plan the smallest integer multiple that covers it.
    """
    nets = _to_decimal_list(net_requirements)
    fq = Decimal(str(fixed_qty))
    if fq <= 0:
        return apply_l4l(net_requirements)
    out = []
    for i, n in enumerate(nets):
        if n <= 0:
            continue
        # ceil(n / fq) using integer math on Decimal
        multiples = int((n + fq - Decimal('0.0001')) // fq)
        out.append((i, fq * multiples))
    return out


def apply_poq(net_requirements, period_count):
    """Period Order Quantity — bucket consecutive periods into one order.

    Groups every ``period_count`` periods. The order is placed in the first
    period of each bucket and covers the sum of net requirements within it.
    """
    nets = _to_decimal_list(net_requirements)
    pc = max(1, int(period_count))
    out = []
    i = 0
    while i < len(nets):
        bucket = nets[i:i + pc]
        bucket_sum = sum(bucket)
        if bucket_sum > 0:
            out.append((i, bucket_sum))
        i += pc
    return out


def apply_min_max(net_requirements, min_qty, max_qty):
    """Min-Max — order between ``min_qty`` and ``max_qty`` to cover net.

    If net <= 0: skip. If net < min: order min. If net > max: order max
    (and the shortfall surfaces as an exception elsewhere).
    """
    nets = _to_decimal_list(net_requirements)
    lo = Decimal(str(min_qty))
    hi = Decimal(str(max_qty))
    if hi <= 0:
        return apply_l4l(net_requirements)
    if lo > hi:
        lo = hi
    out = []
    for i, n in enumerate(nets):
        if n <= 0:
            continue
        planned = max(lo, min(n, hi))
        out.append((i, planned))
    return out


METHOD_DISPATCH = {
    'l4l': apply_l4l,
    'foq': apply_foq,
    'poq': apply_poq,
    'min_max': apply_min_max,
}


def apply(method, net_requirements, *, lot_size_value=Decimal('0'), lot_size_max=Decimal('0')):
    """Dispatch helper used by the MRP engine."""
    if method == 'foq':
        return apply_foq(net_requirements, lot_size_value)
    if method == 'poq':
        return apply_poq(net_requirements, lot_size_value or 1)
    if method == 'min_max':
        return apply_min_max(net_requirements, lot_size_value, lot_size_max)
    return apply_l4l(net_requirements)
