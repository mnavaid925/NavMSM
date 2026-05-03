"""Cycle counting helpers — pure functions.

`classify_abc(consumption_by_product, top_pct=0.20, mid_pct=0.30)` returns
`{product_id: 'A' | 'B' | 'C'}` based on Pareto distribution of consumption
value. Top 20% by value -> A; next 30% -> B; rest -> C.

`compute_variance(system_qty, counted_qty)` returns a tuple
`(variance, variance_pct, recount_required)` where `recount_required` is True
when the absolute variance exceeds 5% of the system qty (configurable via
the `recount_threshold` arg).
"""
from decimal import Decimal


def classify_abc(consumption_by_product, top_pct=Decimal('0.20'), mid_pct=Decimal('0.30')):
    """Return `{product_id: 'A' | 'B' | 'C'}` from a `{product_id: value}` map.

    Pareto distribution over total consumption value, deterministic ordering on
    ties (descending value, then ascending id).
    """
    if not consumption_by_product:
        return {}

    items = sorted(
        consumption_by_product.items(),
        key=lambda kv: (-Decimal(kv[1]), kv[0]),
    )
    n = len(items)
    a_cut = max(1, int(round(n * float(top_pct))))
    b_cut = max(a_cut + 1, int(round(n * (float(top_pct) + float(mid_pct)))))

    result = {}
    for i, (pid, _) in enumerate(items):
        if i < a_cut:
            result[pid] = 'A'
        elif i < b_cut:
            result[pid] = 'B'
        else:
            result[pid] = 'C'
    return result


def compute_variance(system_qty, counted_qty, recount_threshold=Decimal('0.05')):
    """Return (variance, variance_pct, recount_required)."""
    sys_q = Decimal(system_qty)
    cnt_q = Decimal(counted_qty)
    variance = cnt_q - sys_q
    if sys_q == 0:
        variance_pct = Decimal('0') if cnt_q == 0 else Decimal('100')
    else:
        variance_pct = (abs(variance) / sys_q) * Decimal('100')
    recount_required = variance_pct > (Decimal(recount_threshold) * Decimal('100'))
    return variance, variance_pct, recount_required
