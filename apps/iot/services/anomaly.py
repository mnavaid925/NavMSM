"""Module 15 - Heuristic anomaly detection services.

Pure-function implementations matching apps/qms/services/spc.py and
apps/eam/services/prediction.py patterns. No ML library dependency.

Detector menu:
    * threshold_high / threshold_low / range_outside  - simple comparison
    * rate_of_change  - first-difference vs threshold
    * missing_data    - silence longer than window_seconds
    * zscore          - rolling Z (>= 3 sigma flag)
    * iqr             - Tukey IQR fence (>= 1.5 IQR outside Q1/Q3)
    * runs_rule       - Western-Electric Rule 1: any point beyond 3 sigma

Each evaluator returns (matched: bool, baseline: Decimal|None,
                       deviation: Decimal|None).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from statistics import mean, stdev
from typing import Iterable, Optional, Tuple

EvalResult = Tuple[bool, Optional[Decimal], Optional[Decimal]]


def _to_floats(values: Iterable) -> list[float]:
    out: list[float] = []
    for v in values:
        if v is None:
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError, InvalidOperation):
            continue
    return out


def threshold_high(value, threshold) -> EvalResult:
    if value is None or threshold is None:
        return False, None, None
    over = Decimal(value) - Decimal(threshold)
    return (over > 0, Decimal(threshold), over)


def threshold_low(value, threshold) -> EvalResult:
    if value is None or threshold is None:
        return False, None, None
    under = Decimal(threshold) - Decimal(value)
    return (under > 0, Decimal(threshold), under)


def range_outside(value, low, high) -> EvalResult:
    if value is None or low is None or high is None:
        return False, None, None
    v = Decimal(value)
    lo = Decimal(low)
    hi = Decimal(high)
    mid = (lo + hi) / Decimal(2)
    if v < lo:
        return True, mid, lo - v
    if v > hi:
        return True, mid, v - hi
    return False, mid, Decimal('0')


def rolling_zscore(value, history, sigma_threshold=3) -> EvalResult:
    """Z-score against ``history`` (latest first or last - order doesn't matter).

    Returns matched=True when |z| >= sigma_threshold.
    """
    nums = _to_floats(history)
    if value is None or len(nums) < 5:
        return False, None, None
    mu = mean(nums)
    try:
        sigma = stdev(nums)
    except Exception:  # noqa: BLE001
        return False, Decimal(str(mu)), None
    if sigma == 0:
        return False, Decimal(str(mu)), Decimal('0')
    z = (float(value) - mu) / sigma
    return (abs(z) >= sigma_threshold, Decimal(str(mu)), Decimal(str(z)).quantize(Decimal('0.0001')))


def iqr_outlier(value, history, fence=Decimal('1.5')) -> EvalResult:
    """Tukey IQR fence test."""
    nums = sorted(_to_floats(history))
    if value is None or len(nums) < 4:
        return False, None, None
    n = len(nums)
    q1 = nums[n // 4]
    q3 = nums[(3 * n) // 4]
    iqr = q3 - q1
    if iqr == 0:
        return False, Decimal(str((q1 + q3) / 2)), Decimal('0')
    fence_f = float(fence)
    low = q1 - fence_f * iqr
    high = q3 + fence_f * iqr
    v = float(value)
    matched = v < low or v > high
    deviation = max(low - v, v - high, 0)
    return (matched, Decimal(str((q1 + q3) / 2)), Decimal(str(deviation)).quantize(Decimal('0.0001')))


def runs_rule(value, history, sigma_threshold=3) -> EvalResult:
    """Western Electric Rule 1: any single point beyond 3 sigma.

    Subset of the four classic rules (see apps/qms/services/spc.py for the
    full set on subgroups). For a single-point stream we only need rule 1.
    """
    return rolling_zscore(value, history, sigma_threshold)


def evaluate_rule(rule, reading, history) -> EvalResult:
    """Dispatch by rule.condition_type. ``history`` is a list of past values."""
    cond = rule.condition_type
    v = reading.value_numeric

    if cond == 'threshold_high':
        return threshold_high(v, rule.threshold_high)
    if cond == 'threshold_low':
        return threshold_low(v, rule.threshold_low)
    if cond == 'range_outside':
        return range_outside(v, rule.threshold_low, rule.threshold_high)
    if cond == 'rate_of_change':
        if v is None or not history:
            return False, None, None
        try:
            prev = float(history[-1])
        except (TypeError, ValueError, InvalidOperation):
            return False, None, None
        delta = float(v) - prev
        thresh = float(rule.threshold_high) if rule.threshold_high else 0
        return (abs(delta) > thresh, Decimal(str(prev)), Decimal(str(delta)).quantize(Decimal('0.0001')))
    if cond == 'missing_data':
        # The signal layer is responsible for invoking this branch on a
        # silence timer; if invoked here with a present reading, no match.
        return False, None, None
    if cond == 'zscore':
        return rolling_zscore(v, history)
    if cond == 'iqr':
        return iqr_outlier(v, history)
    if cond == 'runs_rule':
        return runs_rule(v, history)
    return False, None, None
