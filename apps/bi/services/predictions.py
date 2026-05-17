"""Pure-Python heuristic forecasters.

No NumPy / pandas / scikit-learn dependency. Every routine takes a list of
``Decimal`` (or coercible numeric) values and returns a list of predictions
plus optional confidence interval halves.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, List, Optional, Sequence, Tuple


ZERO = Decimal('0')


def _to_dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


# ---------------------------------------------------------------------------
# Pure math primitives
# ---------------------------------------------------------------------------

def linear_regression(values: Sequence[Decimal]) -> Tuple[Decimal, Decimal, Decimal]:
    """Ordinary least squares for ``y_i = slope*i + intercept`` (i is zero-based).

    Returns ``(slope, intercept, r_squared)``. Returns zeros for n < 2.
    """
    n = len(values)
    if n < 2:
        return ZERO, ZERO, ZERO
    xs = [Decimal(i) for i in range(n)]
    ys = [_to_dec(v) for v in values]
    sum_x = sum(xs)
    sum_y = sum(ys)
    mean_x = sum_x / Decimal(n)
    mean_y = sum_y / Decimal(n)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return ZERO, mean_y, ZERO
    slope = num / den
    intercept = mean_y - slope * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = ZERO if ss_tot == 0 else (Decimal('1') - (ss_res / ss_tot))
    if r2 < 0:
        r2 = ZERO
    return slope.quantize(Decimal('0.000001')), intercept.quantize(Decimal('0.000001')), r2.quantize(Decimal('0.0001'))


def linear_regression_forecast(
    values: Sequence[Decimal], horizon: int,
) -> List[Tuple[Decimal, Decimal, Decimal]]:
    """Project ``horizon`` periods forward from a linear fit.

    Returns a list of ``(predicted, lower, upper)`` tuples. The CI half-width
    is one residual standard error.
    """
    n = len(values)
    if n < 2 or horizon <= 0:
        return []
    slope, intercept, _r2 = linear_regression(values)
    # Residual standard error
    ys = [_to_dec(v) for v in values]
    residuals = [ys[i] - (slope * Decimal(i) + intercept) for i in range(n)]
    if n > 2:
        var = sum(r * r for r in residuals) / Decimal(n - 2)
        se = var.sqrt() if hasattr(var, 'sqrt') else Decimal(str(float(var) ** 0.5))
    else:
        se = ZERO
    out = []
    for k in range(1, horizon + 1):
        x = Decimal(n - 1 + k)
        yhat = slope * x + intercept
        out.append((yhat.quantize(Decimal('0.0001')),
                    (yhat - se).quantize(Decimal('0.0001')),
                    (yhat + se).quantize(Decimal('0.0001'))))
    return out


def rolling_average(values: Sequence[Decimal], window: int) -> List[Decimal]:
    """Trailing rolling average. Shorter windows at the start are filled with
    the available prefix mean (no NaN)."""
    if window <= 0:
        return []
    out = []
    ys = [_to_dec(v) for v in values]
    for i in range(len(ys)):
        lo = max(0, i - window + 1)
        chunk = ys[lo:i + 1]
        out.append(sum(chunk) / Decimal(len(chunk)))
    return out


def rolling_failure_rate(event_dates: Iterable[date], window_days: int, anchor: date) -> Decimal:
    """Count failure events in the trailing ``window_days`` from ``anchor``."""
    dates = list(event_dates)
    if not dates:
        return ZERO
    cutoff = anchor - timedelta(days=window_days)
    return Decimal(sum(1 for d in dates if cutoff <= d <= anchor))


def naive_seasonal(values: Sequence[Decimal], period_length: int, horizon: int) -> List[Decimal]:
    """Naive seasonal projection: ``yhat[t+h] = y[t+h - period_length]``."""
    if period_length <= 0 or horizon <= 0:
        return []
    ys = [_to_dec(v) for v in values]
    n = len(ys)
    if n < period_length:
        last = ys[-1] if ys else ZERO
        return [last] * horizon
    out = []
    for k in range(1, horizon + 1):
        idx = n - period_length + ((k - 1) % period_length)
        if idx < 0 or idx >= n:
            out.append(ys[-1])
        else:
            out.append(ys[idx])
    return out


def chart_trend(points: Sequence[Decimal]) -> Tuple[Decimal, Decimal, Decimal, str]:
    """Trend summary for an SPC chart series.

    Returns ``(slope, r_squared, last_value, direction)`` where direction is
    one of ``'improving' | 'steady' | 'worsening'`` interpreted as
    "smaller variance is better".
    """
    slope, _, r2 = linear_regression(points)
    last = _to_dec(points[-1]) if points else ZERO
    if abs(slope) < Decimal('0.0001'):
        direction = 'steady'
    elif slope > 0:
        direction = 'worsening'  # rising drift is bad for an SPC series
    else:
        direction = 'improving'
    return slope, r2, last, direction


# ---------------------------------------------------------------------------
# High-level entry points called by views / runs
# ---------------------------------------------------------------------------

def run_demand_forecast(predictive_model, tenant) -> List[dict]:
    """Forecast next ``forecast_horizon_days`` of demand per product.

    Reads `mes.ProductionReport.good_qty` summed per day per product over the
    last ``lookback_days``; fits a linear model; projects forward. Returns
    a list of dicts shaped for ``PredictionResult.objects.create()``.
    """
    from datetime import date as _date
    from django.db.models import Sum
    from apps.mes.models import ProductionReport

    today = _date.today()
    start = today - timedelta(days=predictive_model.lookback_days)
    qs = (
        ProductionReport.all_objects
        .filter(tenant=tenant, reported_at__date__gte=start, reported_at__date__lte=today)
        .values('work_order_operation__work_order__production_order__product_id',
                'work_order_operation__work_order__production_order__product__sku',
                'reported_at__date')
        .annotate(qty=Sum('good_qty'))
        .order_by('work_order_operation__work_order__production_order__product_id', 'reported_at__date')
    )

    series_by_product: dict = {}
    label_by_product: dict = {}
    for row in qs:
        pid = row['work_order_operation__work_order__production_order__product_id']
        if pid is None:
            continue
        sku = row['work_order_operation__work_order__production_order__product__sku'] or ''
        label_by_product[pid] = sku
        series_by_product.setdefault(pid, []).append(_to_dec(row['qty'] or 0))

    results = []
    for pid, series in series_by_product.items():
        if len(series) < 3:
            continue
        forecasts = linear_regression_forecast(series, predictive_model.forecast_horizon_days)
        for k, (pred, lo, hi) in enumerate(forecasts, start=1):
            results.append({
                'target_type': 'product',
                'target_pk': pid,
                'target_label': label_by_product.get(pid, ''),
                'period_date': today + timedelta(days=k),
                'predicted_value': max(pred, ZERO),
                'lower_bound': max(lo, ZERO),
                'upper_bound': hi,
                'confidence_pct': Decimal('60'),
            })
    return results


def run_failure_likelihood(predictive_model, tenant) -> List[dict]:
    """Estimate failure probability per asset from breakdown history."""
    from datetime import date as _date
    try:
        from apps.eam.models import MaintenanceWorkOrder, Asset
    except ImportError:
        return []
    today = _date.today()
    start = today - timedelta(days=predictive_model.lookback_days)
    horizon = predictive_model.forecast_horizon_days

    results = []
    assets = Asset.all_objects.filter(tenant=tenant, status='active')
    for asset in assets:
        breakdowns = list(
            MaintenanceWorkOrder.all_objects
            .filter(tenant=tenant, asset=asset, wo_type='breakdown',
                    created_at__date__gte=start, created_at__date__lte=today)
            .values_list('created_at__date', flat=True)
        )
        rate = rolling_failure_rate(breakdowns, predictive_model.lookback_days, today)
        if rate == 0:
            continue
        likelihood = min((rate / Decimal(predictive_model.lookback_days)) * Decimal(horizon) * Decimal('100'),
                         Decimal('100'))
        results.append({
            'target_type': 'asset',
            'target_pk': asset.pk,
            'target_label': asset.tag or '',
            'period_date': today + timedelta(days=horizon),
            'predicted_value': likelihood.quantize(Decimal('0.01')),
            'lower_bound': (likelihood * Decimal('0.7')).quantize(Decimal('0.01')),
            'upper_bound': (likelihood * Decimal('1.3')).quantize(Decimal('0.01')),
            'confidence_pct': Decimal('55'),
        })
    return results


def run_quality_trend(predictive_model, tenant) -> List[dict]:
    """Compute trend stats on every active SPC chart for the tenant."""
    from datetime import date as _date
    try:
        from apps.qms.models import SPCChart, ControlChartPoint
    except ImportError:
        return []
    today = _date.today()
    horizon = predictive_model.forecast_horizon_days
    results = []
    charts = SPCChart.all_objects.filter(tenant=tenant)
    for chart in charts:
        pts = list(
            ControlChartPoint.all_objects
            .filter(tenant=tenant, chart=chart)
            .order_by('-recorded_at')[:predictive_model.lookback_days]
        )
        if len(pts) < 5:
            continue
        values = list(reversed([p.value for p in pts]))
        slope, _intercept, r2 = linear_regression(values)
        projection = values[-1] + slope * Decimal(horizon)
        results.append({
            'target_type': 'spc_chart',
            'target_pk': chart.pk,
            'target_label': getattr(chart, 'name', f'Chart {chart.pk}'),
            'period_date': today + timedelta(days=horizon),
            'predicted_value': projection.quantize(Decimal('0.0001')),
            'lower_bound': None,
            'upper_bound': None,
            'confidence_pct': (r2 * Decimal('100')).quantize(Decimal('0.01')),
        })
    return results


# Dispatch table keyed by PredictiveModel.code
PREDICTION_REGISTRY = {
    'demand_forecast': run_demand_forecast,
    'failure_likelihood': run_failure_likelihood,
    'quality_trend': run_quality_trend,
    # The drift variants reuse the linear-regression helpers; they're stubbed
    # to demand_forecast for v1 so seed data renders.
    'scrap_drift': run_quality_trend,
    'cost_drift': run_demand_forecast,
    'energy_drift': run_demand_forecast,
}


def run_prediction(predictive_model) -> Tuple[int, List[dict]]:
    """Top-level entry: dispatch + return (result_count, result_dicts).

    The caller is responsible for opening / closing the ``PredictionRun``
    row and creating the ``PredictionResult`` children inside an atomic
    block.
    """
    fn = PREDICTION_REGISTRY.get(predictive_model.code)
    if fn is None:
        raise ValueError(f'Unknown predictive model code: {predictive_model.code!r}')
    rows = fn(predictive_model, predictive_model.tenant)
    return len(rows), rows
