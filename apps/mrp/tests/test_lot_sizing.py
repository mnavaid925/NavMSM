"""Pure-function unit tests for apps.mrp.services.lot_sizing."""
from decimal import Decimal

import pytest

from apps.mrp.services import lot_sizing as ls


class TestL4L:
    def test_picks_only_positive_periods(self):
        out = ls.apply_l4l([0, 5, 0, 10])
        assert out == [(1, Decimal('5')), (3, Decimal('10'))]

    def test_all_zero_history_yields_empty(self):
        assert ls.apply_l4l([0, 0, 0]) == []


class TestFOQ:
    def test_ceil_to_smallest_multiple(self):
        assert ls.apply_foq([75], fixed_qty=50) == [(0, Decimal('100'))]

    def test_exact_multiple(self):
        assert ls.apply_foq([0, 50], fixed_qty=50) == [(1, Decimal('50'))]

    def test_zero_fixed_qty_falls_back_to_l4l(self):
        assert ls.apply_foq([5], fixed_qty=0) == [(0, Decimal('5'))]


class TestPOQ:
    def test_buckets_two_periods(self):
        out = ls.apply_poq([10, 5, 8, 0, 3], period_count=2)
        assert out == [(0, Decimal('15')), (2, Decimal('8')), (4, Decimal('3'))]

    def test_zero_period_count_clamped_to_one(self):
        # max(1, int(0)) → 1, so each positive period becomes its own bucket.
        assert ls.apply_poq([0, 5], period_count=0) == [(1, Decimal('5'))]


class TestMinMax:
    @pytest.mark.parametrize('net,lo,hi,expected', [
        (Decimal('15'), 20, 100, [(0, Decimal('20'))]),
        (Decimal('150'), 20, 100, [(0, Decimal('100'))]),
        (Decimal('50'), 20, 100, [(0, Decimal('50'))]),
    ])
    def test_clamping(self, net, lo, hi, expected):
        assert ls.apply_min_max([net], min_qty=lo, max_qty=hi) == expected

    def test_lo_greater_than_hi_coerces_lo(self):
        assert ls.apply_min_max(
            [Decimal('5')], min_qty=50, max_qty=10,
        ) == [(0, Decimal('10'))]

    def test_skip_non_positive(self):
        assert ls.apply_min_max([Decimal('0'), Decimal('-1')], min_qty=10, max_qty=20) == []


class TestApplyDispatcher:
    def test_unknown_method_falls_back_to_l4l(self):
        assert ls.apply('mystery', [Decimal('5')]) == [(0, Decimal('5'))]

    def test_foq_dispatch(self):
        assert ls.apply(
            'foq', [Decimal('60')], lot_size_value=Decimal('50'),
        ) == [(0, Decimal('100'))]

    def test_min_max_dispatch(self):
        assert ls.apply(
            'min_max', [Decimal('15')],
            lot_size_value=Decimal('20'), lot_size_max=Decimal('100'),
        ) == [(0, Decimal('20'))]
