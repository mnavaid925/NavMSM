"""Pure-function forecasting algorithms.

All four methods take a ``list[Decimal]`` of historical values and return
a ``list[Decimal]`` of forecasted values for the next ``horizon`` periods.
No ORM imports, no side effects — fully unit-testable in isolation.

Methods:
    moving_average(history, window, horizon)
    weighted_moving_average(history, weights, horizon)
    simple_exp_smoothing(history, alpha, horizon)
    naive_seasonal(history, seasonal_indices, horizon)
"""
from decimal import Decimal, ROUND_HALF_UP


def _q(value):
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def moving_average(history, window=3, horizon=12):
    """Simple moving average — average of the last ``window`` periods, repeated.

    A single forecast value is computed (the SMA over the trailing window) and
    flat-lined across the horizon. This matches industry MRP convention for
    an SMA forecast that has no trend component.
    """
    if not history:
        return [Decimal('0')] * horizon
    window = max(1, min(int(window), len(history)))
    tail = [Decimal(str(v)) for v in history[-window:]]
    avg = sum(tail) / Decimal(window)
    return [_q(avg)] * horizon


def weighted_moving_average(history, weights, horizon=12):
    """Weighted moving average — weights apply to the last ``len(weights)`` periods.

    Weights are normalized to sum to 1.0 if they don't already. The forecast
    value is repeated across the horizon (no trend).
    """
    if not history or not weights:
        return [Decimal('0')] * horizon
    w = [Decimal(str(x)) for x in weights]
    total = sum(w)
    if total <= 0:
        return [Decimal('0')] * horizon
    w = [x / total for x in w]
    n = min(len(w), len(history))
    tail = [Decimal(str(v)) for v in history[-n:]]
    weights_aligned = w[-n:]
    forecast = sum(v * wi for v, wi in zip(tail, weights_aligned))
    return [_q(forecast)] * horizon


def simple_exp_smoothing(history, alpha=Decimal('0.3'), horizon=12):
    """Simple (Brown's) exponential smoothing.

    L_t = alpha * y_t + (1 - alpha) * L_{t-1}
    Forecast for all horizon periods is the last computed level (flat).
    """
    if not history:
        return [Decimal('0')] * horizon
    a = Decimal(str(alpha))
    if a <= 0 or a > 1:
        a = Decimal('0.3')
    level = Decimal(str(history[0]))
    for v in history[1:]:
        level = a * Decimal(str(v)) + (Decimal('1') - a) * level
    return [_q(level)] * horizon


def naive_seasonal(history, seasonal_indices, horizon=12):
    """Naive seasonal forecast.

    Computes the mean of the trailing one season's history (de-seasonalized)
    then re-applies the seasonal indices for each forecast period.

    seasonal_indices: ``list[Decimal]`` length = season length (12 for
        monthly, 52 for weekly). 1.0 = neutral.
    """
    if not history or not seasonal_indices:
        return [Decimal('0')] * horizon
    season = len(seasonal_indices)
    indices = [Decimal(str(x)) for x in seasonal_indices]
    history_d = [Decimal(str(v)) for v in history]

    # De-seasonalize the trailing season then average
    if len(history_d) >= season:
        tail = history_d[-season:]
        deseasonalized = [
            v / indices[i] if indices[i] > 0 else v
            for i, v in enumerate(tail)
        ]
        baseline = sum(deseasonalized) / Decimal(season)
    else:
        baseline = sum(history_d) / Decimal(len(history_d))

    forecast = []
    for h in range(horizon):
        idx = indices[h % season]
        forecast.append(_q(baseline * idx))
    return forecast


METHOD_DISPATCH = {
    'moving_avg': moving_average,
    'weighted_ma': weighted_moving_average,
    'simple_exp_smoothing': simple_exp_smoothing,
    'naive_seasonal': naive_seasonal,
}


def run_forecast(method, history, params, horizon):
    """Dispatch helper used by the views/seeder.

    Falls back to a flat zero forecast for unknown methods rather than raising,
    so a buggy params blob never 500s the run view — the engine surfaces the
    fallback via ``MRPRun.error_message`` instead.
    """
    fn = METHOD_DISPATCH.get(method)
    if fn is None:
        return [Decimal('0')] * horizon
    if method == 'moving_avg':
        return fn(history, window=int(params.get('window', 3)), horizon=horizon)
    if method == 'weighted_ma':
        return fn(history, weights=params.get('weights') or [1, 1, 1], horizon=horizon)
    if method == 'simple_exp_smoothing':
        return fn(history, alpha=Decimal(str(params.get('alpha', 0.3))), horizon=horizon)
    if method == 'naive_seasonal':
        return fn(history, seasonal_indices=params.get('seasonal_indices') or [1] * 12, horizon=horizon)
    return [Decimal('0')] * horizon
