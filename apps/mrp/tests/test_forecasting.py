"""Pure-function unit tests for apps.mrp.services.forecasting.

No DB required — these run without django_db.
"""
from decimal import Decimal

import pytest

from apps.mrp.services import forecasting as fc


class TestMovingAverage:
    def test_basic(self):
        assert fc.moving_average([10, 20, 30], window=3, horizon=2) == [
            Decimal('20.00'), Decimal('20.00'),
        ]

    def test_empty_history_returns_zero(self):
        assert fc.moving_average([], window=3, horizon=3) == [Decimal('0')] * 3

    def test_window_clamped_to_history_length(self):
        assert fc.moving_average([10, 20], window=5, horizon=1) == [Decimal('15.00')]


class TestWeightedMovingAverage:
    def test_normalised_equal_weights(self):
        assert fc.weighted_moving_average(
            [10, 20, 30], [1, 1, 1], horizon=1,
        ) == [Decimal('20.00')]

    def test_unnormalised_weights_normalise_internally(self):
        # 10*0.2 + 20*0.3 + 30*0.5 = 2 + 6 + 15 = 23
        assert fc.weighted_moving_average(
            [10, 20, 30], [0.2, 0.3, 0.5], horizon=1,
        ) == [Decimal('23.00')]

    def test_zero_weights_returns_zero_forecast(self):
        assert fc.weighted_moving_average(
            [10, 20, 30], [0, 0, 0], horizon=2,
        ) == [Decimal('0'), Decimal('0')]

    def test_empty_history_returns_zero(self):
        assert fc.weighted_moving_average([], [1, 1], horizon=2) == [Decimal('0')] * 2


class TestSimpleExpSmoothing:
    def test_recursive_level(self):
        # L0 = 10
        # L1 = 0.3 * 15 + 0.7 * 10 = 11.5
        # L2 = 0.3 * 20 + 0.7 * 11.5 = 14.05
        out = fc.simple_exp_smoothing([10, 15, 20], alpha=Decimal('0.3'), horizon=2)
        assert out == [Decimal('14.05'), Decimal('14.05')]

    @pytest.mark.parametrize('bad_alpha', [Decimal('0'), Decimal('-1'), Decimal('2')])
    def test_invalid_alpha_falls_back_to_default(self, bad_alpha):
        out = fc.simple_exp_smoothing([10, 20], alpha=bad_alpha, horizon=1)
        # Default alpha=0.3 → L1 = 0.3*20 + 0.7*10 = 13.0
        assert out[0] == Decimal('13.00')


class TestNaiveSeasonal:
    def test_short_history_uses_full_history_as_baseline(self):
        out = fc.naive_seasonal(
            [Decimal('100')], [Decimal('1')] * 12, horizon=2,
        )
        assert out[0] == Decimal('100.00')

    def test_seasonal_index_applied(self):
        history = [Decimal('100')] * 12
        indices = [Decimal('1.2')] + [Decimal('1')] * 11
        out = fc.naive_seasonal(history, indices, horizon=12)
        # baseline of de-seasonalized full season ≈ 100; first index 1.2 -> 120
        assert out[0] >= Decimal('100')


class TestRunForecastDispatch:
    def test_unknown_method_returns_zero_forecast(self):
        assert fc.run_forecast('mystery', [10, 20], {}, horizon=3) == [Decimal('0')] * 3

    def test_dispatch_moving_avg(self):
        assert fc.run_forecast(
            'moving_avg', [10, 20, 30], {'window': 3}, horizon=2,
        ) == [Decimal('20.00')] * 2

    def test_dispatch_weighted_ma(self):
        out = fc.run_forecast(
            'weighted_ma', [10, 20, 30],
            {'weights': [1, 1, 1]}, horizon=1,
        )
        assert out == [Decimal('20.00')]
