"""Module 15 - Edge transform services.

Pure-function transforms applied to a stream of IoTReading rows. No ORM
imports at module level - the caller passes in already-loaded readings or
the StreamMetric snapshot.
"""
from __future__ import annotations

from decimal import Decimal
from statistics import mean
from typing import Iterable, Optional


def _to_decimal_list(values: Iterable) -> list[Decimal]:
    out = []
    for v in values:
        if v is None:
            continue
        try:
            out.append(Decimal(v) if isinstance(v, Decimal) else Decimal(str(v)))
        except Exception:  # noqa: BLE001
            continue
    return out


def rolling_avg(values: Iterable) -> Optional[Decimal]:
    nums = _to_decimal_list(values)
    if not nums:
        return None
    return (sum(nums) / Decimal(len(nums))).quantize(Decimal('0.0001'))


def window_sum(values: Iterable) -> Optional[Decimal]:
    nums = _to_decimal_list(values)
    if not nums:
        return None
    return sum(nums)


def window_min(values: Iterable) -> Optional[Decimal]:
    nums = _to_decimal_list(values)
    return min(nums) if nums else None


def window_max(values: Iterable) -> Optional[Decimal]:
    nums = _to_decimal_list(values)
    return max(nums) if nums else None


def threshold_count(values: Iterable, threshold: Decimal) -> int:
    nums = _to_decimal_list(values)
    return sum(1 for v in nums if v > threshold)


def derivative(values: Iterable) -> Optional[Decimal]:
    """Approximate first derivative: (last - first) / (n - 1)."""
    nums = _to_decimal_list(values)
    if len(nums) < 2:
        return None
    return ((nums[-1] - nums[0]) / Decimal(len(nums) - 1)).quantize(Decimal('0.0001'))


def state_machine(values: Iterable, mapping: dict) -> Optional[str]:
    """Discrete state classifier: returns the mapping[k] for the last value k.

    ``mapping`` example: {0: 'idle', 1: 'running', 2: 'down'}
    """
    nums = _to_decimal_list(values)
    if not nums:
        return None
    key = int(nums[-1])
    return mapping.get(key)


TRANSFORM_REGISTRY = {
    'rolling_avg': rolling_avg,
    'sum': window_sum,
    'min': window_min,
    'max': window_max,
    'derivative': derivative,
}


def apply_edge_transform(processor, readings: Iterable) -> Optional[Decimal]:
    """Dispatch a transform by ``processor.transform_type``.

    Returns the transformed value or None when the input is empty.
    """
    values = [getattr(r, 'value_numeric', None) for r in readings]
    fn = TRANSFORM_REGISTRY.get(processor.transform_type)
    if fn is not None:
        return fn(values)
    if processor.transform_type == 'threshold_count':
        return Decimal(threshold_count(values, processor.threshold_value or Decimal('0')))
    if processor.transform_type == 'state_machine':
        result = state_machine(values, {0: 'idle', 1: 'running', 2: 'down'})
        return Decimal('1') if result == 'running' else Decimal('0')
    return None
