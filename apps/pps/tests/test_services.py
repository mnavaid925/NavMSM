"""Pure-function tests on scheduler / simulator / optimizer."""
from datetime import datetime, time
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.pps.services import optimizer, scheduler


def _calendars(work_center_id):
    cal = {dow: [(time(8, 0), time(17, 0), True)] for dow in range(5)}
    cal.update({5: [], 6: []})
    return {work_center_id: cal}


def _ops():
    return [
        scheduler.OperationRequest(
            sequence=10, operation_name='Op1', work_center_id=1,
            work_center_code='WC-1',
            setup_minutes=Decimal('15'), run_minutes_per_unit=Decimal('5'),
            queue_minutes=Decimal('5'), move_minutes=Decimal('3'),
        ),
        scheduler.OperationRequest(
            sequence=20, operation_name='Op2', work_center_id=1,
            work_center_code='WC-1',
            setup_minutes=Decimal('10'), run_minutes_per_unit=Decimal('8'),
            queue_minutes=Decimal('5'), move_minutes=Decimal('3'),
        ),
    ]


class TestForwardScheduling:
    def test_aware_datetime_input_handled(self):
        """Regression for L-05 — naive vs aware boundary."""
        slots = scheduler.schedule_forward(
            _ops(), start=timezone.now().replace(hour=9, minute=0),
            quantity=Decimal('10'), calendars=_calendars(1),
        )
        assert len(slots) == 2
        assert slots[0].planned_start.tzinfo is not None

    def test_op2_starts_after_op1_ends(self):
        start = datetime(2026, 5, 4, 8, 0)  # Monday 08:00
        slots = scheduler.schedule_forward(
            _ops(), start=start, quantity=Decimal('10'),
            calendars=_calendars(1),
        )
        assert slots[1].planned_start >= slots[0].planned_end

    def test_walk_skips_weekend(self):
        start = datetime(2026, 5, 8, 16, 30)  # Friday 16:30
        slots = scheduler.schedule_forward(
            _ops(), start=start, quantity=Decimal('10'),
            calendars=_calendars(1),
        )
        # Last op must land on Mon-Fri (weekday < 5)
        assert slots[-1].planned_start.weekday() < 5


class TestBackwardScheduling:
    def test_last_op_ends_at_target(self):
        end = datetime(2026, 5, 15, 16, 0)  # Friday 16:00
        slots = scheduler.schedule_backward(
            _ops(), end=end, quantity=Decimal('10'),
            calendars=_calendars(1),
        )
        # Last op planned_end == end (within 1 minute drift).
        assert abs((slots[-1].planned_end - end).total_seconds()) < 60


class TestInfiniteScheduling:
    def test_capacity_blind_lays_back_to_back(self):
        start = datetime(2026, 5, 3, 23, 30)  # Sunday 23:30 (no shift)
        slots = scheduler.schedule_infinite(
            _ops(), start=start, quantity=Decimal('10'),
        )
        assert len(slots) == 2
        # Op2 starts exactly when Op1 ends — no calendar walk.
        assert slots[1].planned_start == slots[0].planned_end


class TestComputeLoad:
    def test_below_threshold_not_bottleneck(self):
        from datetime import date
        d = date(2026, 5, 4)
        out = scheduler.compute_load({d: 100}, {d: 200})
        assert out[d]['utilization_pct'] == Decimal('50.00')
        assert out[d]['is_bottleneck'] is False

    def test_at_threshold_is_bottleneck(self):
        from datetime import date
        d = date(2026, 5, 4)
        out = scheduler.compute_load({d: 95}, {d: 100})
        assert out[d]['utilization_pct'] == Decimal('95.00')
        assert out[d]['is_bottleneck'] is True


@pytest.mark.django_db
class TestOptimizer:
    def test_rush_orders_first(self, acme, draft_mps):
        from apps.pps.models import OptimizationObjective, OptimizationRun
        obj = OptimizationObjective.objects.create(
            tenant=acme, name='X',
            weight_changeovers=Decimal('1'), weight_idle=Decimal('1'),
            weight_lateness=Decimal('2'), weight_priority=Decimal('2'),
        )
        run = OptimizationRun.objects.create(
            tenant=acme, name='R', mps=draft_mps, objective=obj, status='queued',
        )
        orders = [
            {'id': 1, 'product_id': 100, 'priority': 'low', 'requested_end': None, 'minutes': 60},
            {'id': 2, 'product_id': 100, 'priority': 'rush', 'requested_end': None, 'minutes': 60},
            {'id': 3, 'product_id': 200, 'priority': 'normal', 'requested_end': None, 'minutes': 60},
        ]
        result = optimizer.run_optimization(run, orders=orders)
        sequence = result['suggestion_json']['sequence']
        assert sequence.index(2) < sequence.index(1)
        assert sequence.index(2) < sequence.index(3)

    def test_no_negative_improvement(self, acme, draft_mps):
        from apps.pps.models import OptimizationObjective, OptimizationRun
        obj = OptimizationObjective.objects.create(
            tenant=acme, name='X',
            weight_changeovers=Decimal('1'), weight_idle=Decimal('1'),
            weight_lateness=Decimal('1'), weight_priority=Decimal('1'),
        )
        run = OptimizationRun.objects.create(
            tenant=acme, name='R', mps=draft_mps, objective=obj, status='queued',
        )
        # Already optimally grouped — heuristic produces same or better.
        orders = [
            {'id': 1, 'product_id': 100, 'priority': 'normal', 'requested_end': None, 'minutes': 60},
            {'id': 2, 'product_id': 100, 'priority': 'normal', 'requested_end': None, 'minutes': 60},
        ]
        result = optimizer.run_optimization(run, orders=orders)
        assert result['improvement_pct'] >= Decimal('0')
