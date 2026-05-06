"""Pure-function service tests - no DB required for most."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.labor.services import (
    attendance as att_svc,
    cost_allocation as cost_svc,
    competency as comp_svc,
    piece_rate as pr_svc,
    scheduling as sched_svc,
)


# ---------- attendance ----------

class TestAttendanceService:
    def test_compute_worked_minutes_basic(self):
        ci = datetime(2026, 1, 1, 9, 0)
        co = datetime(2026, 1, 1, 17, 30)
        # 8h30m = 510m, minus 30m break = 480m
        assert att_svc.compute_worked_minutes(ci, co, 30) == 480

    def test_compute_worked_minutes_no_break(self):
        ci = datetime(2026, 1, 1, 9, 0)
        co = datetime(2026, 1, 1, 17, 0)
        assert att_svc.compute_worked_minutes(ci, co, 0) == 480

    def test_compute_worked_minutes_missing(self):
        assert att_svc.compute_worked_minutes(None, None, 30) == 0
        assert att_svc.compute_worked_minutes(datetime(2026, 1, 1, 9, 0), None, 0) == 0

    def test_compute_worked_minutes_zero_when_reverse(self):
        ci = datetime(2026, 1, 1, 9, 0)
        co = datetime(2026, 1, 1, 8, 0)
        assert att_svc.compute_worked_minutes(ci, co, 0) == 0

    def test_derive_status_present(self):
        assert att_svc.derive_status(480, 480) == 'present'

    def test_derive_status_absent(self):
        assert att_svc.derive_status(0, 480) == 'absent'

    def test_derive_status_half_day(self):
        # 200/480 ~ 41% < 50%
        assert att_svc.derive_status(200, 480) == 'half_day'

    def test_derive_status_late(self):
        assert att_svc.derive_status(
            450, 480,
            expected_start=time(6, 0), actual_start=time(6, 30),
            late_grace_minutes=10,
        ) == 'late'

    def test_shift_duration_overnight(self):
        assert att_svc.shift_duration_minutes(
            time(22, 0), time(6, 0), is_overnight=True,
        ) == 8 * 60

    def test_shift_duration_normal(self):
        assert att_svc.shift_duration_minutes(time(9, 0), time(17, 0)) == 8 * 60


# ---------- cost allocation ----------

class TestCostAllocationService:
    def test_compute_total_cost(self):
        # 90 min * 20/hr / 60 = 30.00
        assert cost_svc.compute_total_cost(90, Decimal('20')) == Decimal('30.00')

    def test_compute_total_cost_zero(self):
        assert cost_svc.compute_total_cost(0, Decimal('20')) == Decimal('0.00')
        assert cost_svc.compute_total_cost(60, Decimal('0')) == Decimal('0.00')

    def test_lookup_effective_rate_picks_latest(self):
        rates = [
            SimpleNamespace(effective_from=date(2025, 1, 1), effective_to=None,
                            hourly_rate=Decimal('15')),
            SimpleNamespace(effective_from=date(2026, 1, 1), effective_to=None,
                            hourly_rate=Decimal('25')),
        ]
        r = cost_svc.lookup_effective_rate(rates, date(2026, 6, 1))
        assert r == Decimal('25')

    def test_lookup_effective_rate_no_match(self):
        rates = [SimpleNamespace(
            effective_from=date(2025, 1, 1),
            effective_to=date(2025, 6, 30),
            hourly_rate=Decimal('15'),
        )]
        assert cost_svc.lookup_effective_rate(rates, date(2026, 1, 1)) == Decimal('0')

    def test_summarize_by_cost_center(self):
        rows = [
            SimpleNamespace(cost_center_id=1, minutes=60, total_cost=Decimal('20')),
            SimpleNamespace(cost_center_id=1, minutes=30, total_cost=Decimal('10')),
            SimpleNamespace(cost_center_id=2, minutes=15, total_cost=Decimal('5')),
        ]
        out = cost_svc.summarize_by_cost_center(rows)
        assert out[1]['minutes'] == 90
        assert out[1]['total_cost'] == Decimal('30')
        assert out[2]['minutes'] == 15


# ---------- competency ----------

class TestCompetencyService:
    def test_compute_overall_score(self):
        rows = [
            SimpleNamespace(expected_level=4, actual_level=2, skill_id=1),
            SimpleNamespace(expected_level=4, actual_level=4, skill_id=2),
        ]
        # avg(min(2,4)/4, min(4,4)/4) * 100 = avg(0.5, 1.0) * 100 = 75.0
        assert comp_svc.compute_overall_score(rows) == Decimal('75.00')

    def test_compute_overall_score_no_rows(self):
        assert comp_svc.compute_overall_score([]) == Decimal('0')

    def test_gap_summary_sorted(self):
        rows = [
            SimpleNamespace(skill_id=1, expected_level=5, actual_level=3),
            SimpleNamespace(skill_id=2, expected_level=4, actual_level=4),
            SimpleNamespace(skill_id=3, expected_level=5, actual_level=2),
        ]
        out = comp_svc.gap_summary(rows)
        assert out[0][0] == 3  # biggest gap first
        assert out[0][3] == 3
        assert out[-1][3] == 0

    def test_cert_status_active(self):
        today = date(2026, 1, 1)
        assert comp_svc.cert_status_for(date(2026, 6, 1), today) == 'active'

    def test_cert_status_expiring_soon(self):
        today = date(2026, 1, 1)
        assert comp_svc.cert_status_for(date(2026, 1, 15), today) == 'expiring_soon'

    def test_cert_status_expired(self):
        today = date(2026, 1, 1)
        assert comp_svc.cert_status_for(date(2025, 12, 1), today) == 'expired'


# ---------- piece rate ----------

class TestPieceRateService:
    def test_compute_amount(self):
        assert pr_svc.compute_amount(100, Decimal('1.5')) == Decimal('150.00')

    def test_compute_amount_zero(self):
        assert pr_svc.compute_amount(0, Decimal('5')) == Decimal('0.00')
        assert pr_svc.compute_amount(10, Decimal('0')) == Decimal('0.00')

    def test_select_rate_prefers_operation(self):
        product = SimpleNamespace(pk=1)
        operation = SimpleNamespace(pk=10)
        rates = [
            SimpleNamespace(product_id=1, operation_id=None,
                            min_quantity=None, max_quantity=None,
                            rate_per_unit=Decimal('1')),
            SimpleNamespace(product_id=None, operation_id=10,
                            min_quantity=None, max_quantity=None,
                            rate_per_unit=Decimal('2')),
        ]
        chosen = pr_svc.select_rate(rates, product=product, operation=operation, qty=Decimal('1'))
        assert chosen.rate_per_unit == Decimal('2')

    def test_select_rate_quantity_band(self):
        product = SimpleNamespace(pk=1)
        rates = [SimpleNamespace(
            product_id=1, operation_id=None,
            min_quantity=Decimal('100'), max_quantity=None,
            rate_per_unit=Decimal('5'),
        )]
        # qty below band -> no match
        assert pr_svc.select_rate(rates, product=product, qty=Decimal('50')) is None
        # qty above min -> match
        assert pr_svc.select_rate(rates, product=product, qty=Decimal('150')).rate_per_unit == Decimal('5')

    def test_aggregate_employee_units(self):
        rows = [
            SimpleNamespace(reported_by_id=1, good_qty=Decimal('10')),
            SimpleNamespace(reported_by_id=1, good_qty=Decimal('20')),
            SimpleNamespace(reported_by_id=2, good_qty=Decimal('5')),
            SimpleNamespace(reported_by_id=None, good_qty=Decimal('99')),
        ]
        out = pr_svc.aggregate_employee_units(rows)
        assert out[1] == Decimal('30')
        assert out[2] == Decimal('5')
        assert None not in out


# ---------- scheduling ----------

class TestSchedulingService:
    def test_date_range_inclusive(self):
        days = list(sched_svc.date_range(date(2026, 1, 1), date(2026, 1, 3)))
        assert len(days) == 3
        assert days[0] == date(2026, 1, 1)
        assert days[-1] == date(2026, 1, 3)

    def test_date_range_empty_when_reversed(self):
        days = list(sched_svc.date_range(date(2026, 1, 3), date(2026, 1, 1)))
        assert days == []

    def test_split_overlapping_no_overlap(self):
        out = sched_svc.split_overlapping(
            date(2026, 2, 1), date(2026, 2, 28),
            existing_ranges=[(date(2026, 1, 1), date(2026, 1, 31))],
        )
        assert out == [(date(2026, 2, 1), date(2026, 2, 28))]

    def test_split_overlapping_full_engulf(self):
        out = sched_svc.split_overlapping(
            date(2026, 2, 1), date(2026, 2, 5),
            existing_ranges=[(date(2026, 1, 1), date(2026, 12, 31))],
        )
        assert out == []
