"""Heuristic predictive-maintenance classifier.

v1 logic (see Plan Q8):
    - Reading inside [low_alarm, high_alarm]: 'normal'.
    - Reading outside the band but within 20% margin: 'warning'.
    - Reading outside the 20% margin or null-banded with extreme value: 'critical'.

Pure function except for the optional auto-create FailurePrediction helper.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class ClassificationResult:
    status: str   # one of 'normal', 'warning', 'critical'
    breached: bool
    margin_pct: Optional[Decimal]


WARN_MARGIN = Decimal('0.20')   # 20% beyond alarm band before flipping to critical


def classify_reading(value, low_alarm, high_alarm) -> ClassificationResult:
    """Pure: classify a numeric value against an alarm band."""
    if value is None:
        return ClassificationResult(status='normal', breached=False, margin_pct=None)
    val = Decimal(value)
    low = Decimal(low_alarm) if low_alarm is not None else None
    high = Decimal(high_alarm) if high_alarm is not None else None

    if low is None and high is None:
        return ClassificationResult(status='normal', breached=False, margin_pct=None)

    breached_low = low is not None and val < low
    breached_high = high is not None and val > high

    if not (breached_low or breached_high):
        return ClassificationResult(status='normal', breached=False, margin_pct=Decimal('0'))

    # Compute distance beyond the band as a fraction of the band itself
    # (or the alarm value when only one side is defined).
    band = (high - low) if (low is not None and high is not None) else None
    if breached_low:
        anchor = low
        delta = (low - val)
    else:
        anchor = high
        delta = (val - high)

    base = band if band and band > 0 else (abs(anchor) if anchor else Decimal('1'))
    margin = (delta / base) if base else Decimal('0')

    if margin > WARN_MARGIN:
        return ClassificationResult(status='critical', breached=True, margin_pct=margin)
    return ClassificationResult(status='warning', breached=True, margin_pct=margin)


def check_reading(reading) -> ClassificationResult:
    """Classify and persist `status` on an existing ConditionReading.

    Idempotent. Does NOT auto-create a FailurePrediction; the caller decides
    when to escalate (typically the post_save signal handler).
    """
    from apps.eam.models import ConditionReading

    point = reading.point
    cr = classify_reading(reading.reading_value, point.low_alarm, point.high_alarm)
    if reading.status != cr.status:
        ConditionReading.all_objects.filter(pk=reading.pk).update(status=cr.status)
    return cr
