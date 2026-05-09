"""Module 15 - service-layer unit tests.

Covers:
    * services.anomaly: threshold, range, zscore, iqr
    * services.edge: rolling_avg / sum / min / max / threshold_count
    * services.twin._safe_eval: legitimate formulas + injection attempts
"""
from decimal import Decimal

import pytest

from apps.iot.services import anomaly, edge
from apps.iot.services.twin import FormulaError, evaluate_formula


pytestmark = pytest.mark.django_db


# -- Anomaly --------------------------------------------------------------

def test_threshold_high_match():
    matched, baseline, dev = anomaly.threshold_high(Decimal('100'), Decimal('80'))
    assert matched is True
    assert dev == Decimal('20')


def test_threshold_high_no_match():
    matched, baseline, dev = anomaly.threshold_high(Decimal('70'), Decimal('80'))
    assert matched is False


def test_threshold_low_match():
    matched, baseline, dev = anomaly.threshold_low(Decimal('5'), Decimal('10'))
    assert matched is True


def test_range_outside_below_low():
    matched, baseline, dev = anomaly.range_outside(Decimal('5'), Decimal('10'), Decimal('20'))
    assert matched is True


def test_range_outside_inside():
    matched, _, _ = anomaly.range_outside(Decimal('15'), Decimal('10'), Decimal('20'))
    assert matched is False


def test_zscore_no_history():
    matched, _, _ = anomaly.rolling_zscore(100, [50])
    assert matched is False


def test_zscore_outlier():
    history = [10, 11, 9, 10, 11, 10, 9, 11, 10, 9]
    matched, baseline, dev = anomaly.rolling_zscore(100, history, sigma_threshold=3)
    assert matched is True


def test_iqr_outlier_detected():
    history = [10, 11, 9, 10, 12, 10, 11, 9, 10]
    matched, _, _ = anomaly.iqr_outlier(100, history)
    assert matched is True


def test_iqr_normal_value():
    history = [10, 11, 9, 10, 12, 10, 11, 9, 10]
    matched, _, _ = anomaly.iqr_outlier(11, history)
    assert matched is False


# -- Edge transforms ------------------------------------------------------

def test_rolling_avg():
    assert edge.rolling_avg([10, 20, 30]) == Decimal('20.0000')


def test_rolling_avg_empty():
    assert edge.rolling_avg([]) is None


def test_window_min_max():
    assert edge.window_min([3, 1, 2]) == Decimal('1')
    assert edge.window_max([3, 1, 2]) == Decimal('3')


def test_threshold_count():
    assert edge.threshold_count([1, 5, 9, 2, 11], Decimal('5')) == 2


def test_derivative():
    # (last - first) / (n-1) = (10 - 0) / (5 - 1) = 2.5
    assert edge.derivative([0, 2, 5, 8, 10]) == Decimal('2.5000')


# -- Twin safe-formula evaluator ------------------------------------------

def test_formula_basic_arithmetic():
    assert evaluate_formula('1 + 2 * 3', {}) == Decimal('7')


def test_formula_with_variables():
    assert evaluate_formula('temp + offset', {'temp': Decimal('70'), 'offset': Decimal('5')}) == Decimal('75')


def test_formula_min_max_abs():
    ctx = {'a': Decimal('-5'), 'b': Decimal('10')}
    assert evaluate_formula('abs(a)', ctx) == Decimal('5')
    assert evaluate_formula('min(a, b)', ctx) == Decimal('-5')
    assert evaluate_formula('max(a, b)', ctx) == Decimal('10')


def test_formula_division_by_zero_safe():
    assert evaluate_formula('a / b', {'a': Decimal('10'), 'b': Decimal('0')}) == Decimal('0')


def test_formula_rejects_unsafe_call():
    with pytest.raises(FormulaError):
        evaluate_formula('__import__("os").system("whoami")', {})


def test_formula_rejects_attribute_access():
    with pytest.raises(FormulaError):
        evaluate_formula('temp.__class__', {'temp': Decimal('1')})


def test_formula_rejects_unknown_function():
    with pytest.raises(FormulaError):
        evaluate_formula('exec("rm -rf /")', {})


def test_formula_rejects_undefined_variable():
    with pytest.raises(FormulaError):
        evaluate_formula('undefined_var * 2', {})


def test_formula_rejects_disallowed_operator():
    with pytest.raises(FormulaError):
        evaluate_formula('5 ** 2', {})  # power operator not allowed


def test_formula_empty_returns_zero():
    assert evaluate_formula('', {}) == Decimal('0')
    assert evaluate_formula('   ', {}) == Decimal('0')


def test_formula_lambda_rejected():
    with pytest.raises(FormulaError):
        evaluate_formula('(lambda: 1)()', {})
