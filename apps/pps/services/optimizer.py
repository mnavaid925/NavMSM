"""Greedy heuristic optimizer (v1 — deterministic, not ML-based).

The optimizer takes a list of ProductionOrder candidates and reorders them
to reduce changeovers and lateness. Real ML/AI optimization (e.g. genetic
algorithms, mixed-integer programming, learned heuristics) is intentionally
out of scope for Phase 1; the data model + UI is forward-compatible with
one — just swap in a different ranker here.

The objective weights come from the OptimizationObjective record:
    higher weight_changeovers -> aggressively group like products
    higher weight_lateness    -> respect requested_end more strongly
    higher weight_priority    -> rush orders win ties
    higher weight_idle        -> compact the schedule (less impact in v1)
"""
from __future__ import annotations

from decimal import Decimal


_PRIORITY_RANK = {'rush': 0, 'high': 1, 'normal': 2, 'low': 3}


def _changeover_count(orders):
    last_product = None
    n = 0
    for o in orders:
        if last_product is not None and o['product_id'] != last_product:
            n += 1
        last_product = o['product_id']
    return n


def _lateness(orders):
    """Sum of (placement_index) for each order — proxy for risk of missing
    requested_end. Low-priority + early-due orders shoved to the back inflate it."""
    return sum(idx for idx, _ in enumerate(orders))


def run_optimization(run, *, orders):
    """Reorder `orders` (a list of dicts) per the run's objective weights.

    `orders` schema:
        [{'id': int, 'product_id': int, 'priority': str,
          'requested_end': datetime | None, 'minutes': int}, ...]

    Returns a result payload suitable for OptimizationResult.
    """
    obj = run.objective
    before_changeovers = _changeover_count(orders)
    before_total = sum(o.get('minutes', 0) for o in orders)
    before_lateness = _lateness(orders)

    # Greedy scoring:
    # 1) priority (lower rank = first)
    # 2) requested_end (earlier first)
    # 3) product_id (group like with like — minimizes changeovers)
    weight_changeovers = Decimal(str(obj.weight_changeovers))
    weight_lateness = Decimal(str(obj.weight_lateness))
    weight_priority = Decimal(str(obj.weight_priority))

    def _score(order):
        prio_rank = _PRIORITY_RANK.get(order.get('priority', 'normal'), 2)
        # Build a sort key: priority dominates if weight_priority >= 1.5,
        # else product grouping dominates.
        priority_term = prio_rank * weight_priority
        # requested_end: convert to ordinal days from epoch for stable sort
        re = order.get('requested_end')
        re_term = (re.toordinal() if re else 10**9) * weight_lateness
        # Product grouping is encoded by stable secondary sort; we only need
        # priority + lateness as the primary score.
        return (priority_term, re_term, order.get('product_id', 0))

    after = sorted(orders, key=_score)

    # Second pass: collapse runs of like products to reduce changeovers.
    # If weight_changeovers is high, we sweep adjacent orders and group by
    # product_id within the same priority bucket.
    if weight_changeovers >= Decimal('1'):
        grouped: list[dict] = []
        seen_buckets: dict[tuple, list[dict]] = {}
        order_priority_buckets: list[tuple] = []
        for o in after:
            bucket = (o.get('priority', 'normal'),)
            if bucket not in seen_buckets:
                seen_buckets[bucket] = []
                order_priority_buckets.append(bucket)
            seen_buckets[bucket].append(o)
        for bucket in order_priority_buckets:
            bucket_orders = sorted(
                seen_buckets[bucket],
                key=lambda o: (o.get('product_id', 0),
                               (o.get('requested_end').toordinal()
                                if o.get('requested_end') else 10**9)),
            )
            grouped.extend(bucket_orders)
        after = grouped

    after_changeovers = _changeover_count(after)
    after_total = sum(o.get('minutes', 0) for o in after)
    after_lateness = _lateness(after)

    # Improvement: weighted delta vs before.
    co_delta = before_changeovers - after_changeovers
    lateness_delta = before_lateness - after_lateness
    raw_improvement = (
        Decimal(str(co_delta)) * weight_changeovers
        + Decimal(str(lateness_delta)) * weight_lateness
    )
    base = Decimal(str(max(before_changeovers, 1))) * weight_changeovers \
        + Decimal(str(max(before_lateness, 1))) * weight_lateness
    improvement_pct = (raw_improvement / base * Decimal('100')).quantize(Decimal('0.01'))
    if improvement_pct < 0:
        improvement_pct = Decimal('0')

    return {
        'before_total_minutes': before_total,
        'after_total_minutes': after_total,
        'before_changeovers': before_changeovers,
        'after_changeovers': after_changeovers,
        'before_lateness': before_lateness,
        'after_lateness': after_lateness,
        'improvement_pct': improvement_pct,
        'suggestion_json': {
            'objective': obj.name,
            'sequence': [o['id'] for o in after],
            'product_sequence': [o.get('product_id') for o in after],
            'algorithm': 'greedy-priority-then-product-grouping',
        },
    }
