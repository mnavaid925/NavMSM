"""Module 20.5 - Process mining.

Heuristic cycle-time + bottleneck calculations. Pure-ish: the helpers
take querysets / instances and return computed Decimals; the caller
writes ProcessMetric / BottleneckAnalysis / CycleTimeReport rows.

No numpy / scikit-learn dependency - everything is plain Python.
"""
from __future__ import annotations

from decimal import Decimal
from statistics import mean
from typing import Iterable


def _to_seconds(td):
    if td is None:
        return Decimal('0')
    total = td.total_seconds() if hasattr(td, 'total_seconds') else float(td)
    return Decimal(str(round(total, 2)))


def compute_cycle_seconds(instance):
    """Total elapsed seconds from started_at to completed_at."""
    if not instance.started_at or not instance.completed_at:
        return Decimal('0')
    return _to_seconds(instance.completed_at - instance.started_at)


def per_node_wait_seconds(instance):
    """Map ``{node_id: total_wait_seconds}`` for a single instance.

    Wait time = sum of (next-activity timestamp - entered-activity
    timestamp) where event=='entered' and the immediately following
    activity is on a different node.
    """
    acts = list(
        instance.activities.select_related('node')
        .order_by('recorded_at', 'id')
    )
    waits: dict[int, Decimal] = {}
    last_entered = None
    for a in acts:
        if a.node_id is None:
            continue
        if last_entered is not None:
            delta = _to_seconds(a.recorded_at - last_entered.recorded_at)
            waits[last_entered.node_id] = waits.get(last_entered.node_id, Decimal('0')) + delta
        if a.event == 'entered':
            last_entered = a
        elif a.event in ('completed', 'cancelled', 'error'):
            last_entered = None
    return waits


def detect_bottleneck(definition, *, period_start, period_end):
    """Return ``(node, avg_wait_seconds, instance_count)`` for the
    slowest node observed across instances completed within the
    period, or ``(None, 0, 0)`` if no data.
    """
    instances = list(
        definition.instances
        .filter(
            status='completed',
            completed_at__date__gte=period_start,
            completed_at__date__lte=period_end,
        )
    )
    if not instances:
        return None, Decimal('0'), 0
    sums: dict[int, list[Decimal]] = {}
    for inst in instances:
        for node_id, wait in per_node_wait_seconds(inst).items():
            sums.setdefault(node_id, []).append(wait)
    if not sums:
        return None, Decimal('0'), len(instances)
    worst_id, worst_avg = max(
        ((nid, Decimal(str(mean(map(float, vals))))) for nid, vals in sums.items()),
        key=lambda kv: kv[1],
    )
    from apps.wfa.models import ProcessNode
    node = ProcessNode.all_objects.filter(pk=worst_id).first()
    return node, Decimal(str(round(float(worst_avg), 2))), len(instances)


def classify_severity(avg_wait_seconds: Decimal) -> str:
    s = float(avg_wait_seconds)
    if s >= 86400:  # >= 24h
        return 'critical'
    if s >= 14400:  # >= 4h
        return 'high'
    if s >= 1800:  # >= 30min
        return 'medium'
    return 'low'


def cycle_time_stats(instances: Iterable):
    """Return ``(count, avg, p95, min_v, max_v)`` over completed instances."""
    secs = sorted(
        float(compute_cycle_seconds(inst))
        for inst in instances
        if inst.completed_at and inst.started_at
    )
    if not secs:
        return 0, Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0')
    n = len(secs)
    avg = sum(secs) / n
    # nearest-rank p95 (no numpy)
    rank = max(0, int(round(0.95 * n)) - 1)
    p95 = secs[rank]
    return (
        n,
        Decimal(str(round(avg, 2))),
        Decimal(str(round(p95, 2))),
        Decimal(str(round(secs[0], 2))),
        Decimal(str(round(secs[-1], 2))),
    )
