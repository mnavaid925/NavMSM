"""Pure-function supplier scorecard math.

Given a list of `SupplierMetricEvent` rows for a (supplier, period) window,
compute the OTD %, quality rating, defect rate, price variance, and overall
weighted score. All inputs are passed in by the caller; this module never
touches the ORM directly so it is trivially unit-testable.
"""
from dataclasses import dataclass
from decimal import Decimal


# Weights sum to 1.0; tweak here to retune the overall score formula.
WEIGHT_OTD = Decimal('0.40')
WEIGHT_QUALITY = Decimal('0.40')
WEIGHT_RESPONSIVENESS = Decimal('0.10')
WEIGHT_PRICE = Decimal('0.10')


@dataclass
class ScorecardResult:
    otd_pct: Decimal
    quality_rating: Decimal
    defect_rate_pct: Decimal
    price_variance_pct: Decimal
    responsiveness_rating: Decimal
    overall_score: Decimal


def _pct(numerator, denominator):
    if not denominator:
        return Decimal('0')
    return (Decimal(numerator) * Decimal('100') / Decimal(denominator)).quantize(Decimal('0.01'))


def compute_scorecard(events):
    """Compute KPIs from an iterable of SupplierMetricEvent-like dicts.

    Each event is expected to have ``event_type`` and ``value`` attributes
    (or dict keys). Pure function - no ORM access.
    """
    on_time = late = passes = fails = responses = missed = 0
    price_variance_sum = Decimal('0')
    price_variance_count = 0

    for ev in events:
        et = getattr(ev, 'event_type', None) or ev['event_type']
        val = getattr(ev, 'value', None)
        if val is None:
            val = ev.get('value', Decimal('0'))
        val = Decimal(val) if not isinstance(val, Decimal) else val

        if et == 'po_received_on_time':
            on_time += 1
        elif et == 'po_received_late':
            late += 1
        elif et == 'quality_pass':
            passes += 1
        elif et == 'quality_fail':
            fails += 1
        elif et == 'price_variance':
            price_variance_sum += val
            price_variance_count += 1
        elif et == 'response_received':
            responses += 1
        elif et == 'response_missed':
            missed += 1

    total_pos = on_time + late
    total_qc = passes + fails
    total_resp = responses + missed

    otd_pct = _pct(on_time, total_pos)
    quality_rating = _pct(passes, total_qc)
    defect_rate_pct = _pct(fails, total_qc)
    responsiveness_rating = _pct(responses, total_resp)
    price_variance_pct = (
        (price_variance_sum / Decimal(price_variance_count)).quantize(Decimal('0.01'))
        if price_variance_count else Decimal('0')
    )

    # Price-variance contribution: 100 - |variance| (clipped to [0, 100]).
    # When there's no price data, contribute 0 (not a free 100). Otherwise an
    # all-zero supplier scores ~10 just from the price weight, which is wrong.
    if price_variance_count:
        price_score = max(Decimal('0'), Decimal('100') - abs(price_variance_pct))
        price_score = min(Decimal('100'), price_score)
    else:
        price_score = Decimal('0')

    overall = (
        otd_pct * WEIGHT_OTD
        + quality_rating * WEIGHT_QUALITY
        + responsiveness_rating * WEIGHT_RESPONSIVENESS
        + price_score * WEIGHT_PRICE
    ).quantize(Decimal('0.01'))

    return ScorecardResult(
        otd_pct=otd_pct,
        quality_rating=quality_rating,
        defect_rate_pct=defect_rate_pct,
        price_variance_pct=price_variance_pct,
        responsiveness_rating=responsiveness_rating,
        overall_score=overall,
    )
