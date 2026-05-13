"""Pure-function service tests (registry, kpi classification, predictions math)."""
from decimal import Decimal

import pytest

from apps.bi.services import registry as registry_svc
from apps.bi.services import kpi as kpi_svc
from apps.bi.services import predictions as pred_svc


class TestRegistry:
    def test_get_source_returns_known(self):
        info = registry_svc.get_source('production_orders')
        assert info is not None
        assert info['model_label'] == 'pps.ProductionOrder'

    def test_get_source_returns_none_for_unknown(self):
        assert registry_svc.get_source('not-a-thing') is None

    def test_assert_field_allowed_accepts_whitelisted(self):
        registry_svc.assert_field_allowed('production_orders', 'order_number')

    def test_assert_field_allowed_rejects_unknown_source(self):
        with pytest.raises(ValueError):
            registry_svc.assert_field_allowed('nope', 'order_number')

    def test_assert_field_allowed_rejects_unwhitelisted_field(self):
        with pytest.raises(ValueError):
            registry_svc.assert_field_allowed('production_orders', 'password_hash')

    def test_list_sources_returns_tuples(self):
        srcs = registry_svc.list_sources()
        assert len(srcs) > 0
        assert all(len(s) == 3 for s in srcs)


@pytest.mark.django_db
class TestKPIClassification:
    def test_higher_is_better_on_target(self, oee_kpi):
        assert kpi_svc.classify_value(oee_kpi, Decimal('90')) == 'on_target'

    def test_higher_is_better_warning(self, oee_kpi):
        assert kpi_svc.classify_value(oee_kpi, Decimal('65')) == 'warning'

    def test_higher_is_better_critical(self, oee_kpi):
        assert kpi_svc.classify_value(oee_kpi, Decimal('50')) == 'critical'

    def test_lower_is_better_on_target(self, acme):
        from apps.bi import models as B
        scrap = B.KPIDefinition.objects.create(
            tenant=acme, code='scrap_rate', name='Scrap', direction='lower_is_better',
            target_value=Decimal('2'), warning_threshold=Decimal('5'), critical_threshold=Decimal('10'),
        )
        assert kpi_svc.classify_value(scrap, Decimal('1')) == 'on_target'
        assert kpi_svc.classify_value(scrap, Decimal('6')) == 'warning'
        assert kpi_svc.classify_value(scrap, Decimal('11')) == 'critical'

    def test_no_thresholds_always_on_target(self, throughput_kpi):
        assert kpi_svc.classify_value(throughput_kpi, Decimal('5')) == 'on_target'
        assert kpi_svc.classify_value(throughput_kpi, Decimal('-100')) == 'on_target'


class TestLinearRegression:
    def test_perfect_line(self):
        slope, intercept, r2 = pred_svc.linear_regression([1, 2, 3, 4, 5])
        assert abs(slope - Decimal('1')) < Decimal('0.001')
        assert abs(intercept - Decimal('1')) < Decimal('0.001')
        assert r2 == Decimal('1.0000')

    def test_flat_line(self):
        slope, intercept, r2 = pred_svc.linear_regression([5, 5, 5, 5])
        assert slope == Decimal('0')
        assert intercept == Decimal('5')
        assert r2 == Decimal('0')

    def test_short_series(self):
        slope, intercept, r2 = pred_svc.linear_regression([1])
        assert slope == Decimal('0')
        assert intercept == Decimal('0')

    def test_forecast_horizon(self):
        out = pred_svc.linear_regression_forecast([1, 2, 3, 4, 5], 3)
        assert len(out) == 3
        # Next values should be ~6, 7, 8
        assert abs(out[0][0] - Decimal('6')) < Decimal('0.01')

    def test_forecast_zero_horizon(self):
        out = pred_svc.linear_regression_forecast([1, 2, 3], 0)
        assert out == []


class TestRollingAverage:
    def test_rolling_average(self):
        out = pred_svc.rolling_average([10, 20, 30, 40], window=2)
        assert len(out) == 4
        assert out[0] == Decimal('10')
        assert out[1] == Decimal('15')
        assert out[2] == Decimal('25')

    def test_rolling_average_window_zero(self):
        assert pred_svc.rolling_average([1, 2, 3], 0) == []


class TestChartTrend:
    def test_improving_series(self):
        slope, r2, last, direction = pred_svc.chart_trend([5, 4, 3, 2, 1])
        assert slope < Decimal('0')
        assert direction == 'improving'

    def test_worsening_series(self):
        slope, r2, last, direction = pred_svc.chart_trend([1, 2, 3, 4, 5])
        assert slope > Decimal('0')
        assert direction == 'worsening'

    def test_steady_series(self):
        slope, r2, last, direction = pred_svc.chart_trend([5, 5, 5, 5])
        assert direction == 'steady'


class TestNaiveSeasonal:
    def test_period_12_horizon_3(self):
        values = list(range(12))
        out = pred_svc.naive_seasonal(values, period_length=12, horizon=3)
        assert len(out) == 3

    def test_short_series_returns_last(self):
        out = pred_svc.naive_seasonal([7], period_length=12, horizon=3)
        assert out == [Decimal('7'), Decimal('7'), Decimal('7')]
