"""Tests for the pure-function MES services (dispatcher, time-logging, reporting)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.mes.models import (
    MESWorkOrder, MESWorkOrderOperation, OperatorTimeLog, ProductionReport,
)
from apps.mes.services import dispatcher, reporting, time_logging


# ============================================================================
# Dispatcher
# ============================================================================

@pytest.mark.django_db
class TestDispatcher:
    def test_creates_work_order_with_one_op_per_routing_op(self, released_po, acme_admin):
        wo = dispatcher.dispatch_production_order(released_po, dispatched_by=acme_admin)
        assert wo.wo_number.startswith('WO-')
        assert wo.product == released_po.product
        assert wo.quantity_to_build == released_po.quantity
        # The seeded routing has 2 operations
        assert wo.operations.count() == 2

    def test_planned_orders_rejected(self, planned_po, acme_admin):
        with pytest.raises(dispatcher.DispatchError):
            dispatcher.dispatch_production_order(planned_po, dispatched_by=acme_admin)

    def test_routing_none_rejected(self, released_po, acme_admin):
        released_po.routing = None
        released_po.save()
        with pytest.raises(dispatcher.DispatchError):
            dispatcher.dispatch_production_order(released_po, dispatched_by=acme_admin)

    def test_idempotent_returns_existing(self, released_po, acme_admin):
        first = dispatcher.dispatch_production_order(released_po, dispatched_by=acme_admin)
        second = dispatcher.dispatch_production_order(released_po, dispatched_by=acme_admin)
        assert first.pk == second.pk
        # Still exactly one work order, not two
        assert MESWorkOrder.objects.filter(production_order=released_po).count() == 1

    def test_cancelled_wo_does_not_block_re_dispatch(self, released_po, acme_admin):
        wo1 = dispatcher.dispatch_production_order(released_po, dispatched_by=acme_admin)
        wo1.status = 'cancelled'
        wo1.save()
        wo2 = dispatcher.dispatch_production_order(released_po, dispatched_by=acme_admin)
        assert wo2.pk != wo1.pk
        assert wo2.status == 'dispatched'

    def test_op_planned_minutes_match_routing_total(self, released_po, acme_admin):
        wo = dispatcher.dispatch_production_order(released_po, dispatched_by=acme_admin)
        first = wo.operations.order_by('sequence').first()
        # Cut op: 15 setup + 5*10 run + 5 queue + 3 move = 73
        assert first.planned_minutes == Decimal('73.00')


# ============================================================================
# Time logging — pure compute_actual_minutes helper + integration record_event
# ============================================================================

class _FakeLog:
    """Lightweight stand-in matching the OperatorTimeLog row shape."""
    def __init__(self, action, recorded_at):
        self.action = action
        self.recorded_at = recorded_at


class TestComputeActualMinutesPure:
    def test_single_start_stop_pair(self):
        t0 = timezone.now()
        logs = [
            _FakeLog('start_job', t0),
            _FakeLog('stop_job', t0 + timedelta(minutes=30)),
        ]
        assert time_logging.compute_actual_minutes(logs) == Decimal('30.00')

    def test_pause_resume_stop(self):
        t0 = timezone.now()
        logs = [
            _FakeLog('start_job', t0),
            _FakeLog('pause_job', t0 + timedelta(minutes=10)),
            _FakeLog('resume_job', t0 + timedelta(minutes=20)),
            _FakeLog('stop_job', t0 + timedelta(minutes=30)),
        ]
        # 10 + 10 = 20 minutes worked
        assert time_logging.compute_actual_minutes(logs) == Decimal('20.00')

    def test_open_run_clamped_to_now(self):
        t0 = timezone.now() - timedelta(minutes=15)
        now = timezone.now()
        logs = [_FakeLog('start_job', t0)]
        result = time_logging.compute_actual_minutes(logs, now=now)
        # ~15 minutes elapsed, allow for slight tolerance
        assert Decimal('14.5') <= result <= Decimal('15.5')

    def test_unsorted_input_handled(self):
        t0 = timezone.now()
        logs = [
            _FakeLog('stop_job', t0 + timedelta(minutes=20)),
            _FakeLog('start_job', t0),
        ]
        assert time_logging.compute_actual_minutes(logs) == Decimal('20.00')

    def test_clock_in_out_ignored(self):
        t0 = timezone.now()
        logs = [
            _FakeLog('clock_in', t0),
            _FakeLog('start_job', t0 + timedelta(minutes=5)),
            _FakeLog('stop_job', t0 + timedelta(minutes=15)),
            _FakeLog('clock_out', t0 + timedelta(minutes=20)),
        ]
        assert time_logging.compute_actual_minutes(logs) == Decimal('10.00')


@pytest.mark.django_db
class TestRecordEvent:
    def test_start_job_flips_op_to_running_and_wo_to_in_progress(self, operator, first_op):
        time_logging.record_event(operator, 'start_job', work_order_operation=first_op)
        first_op.refresh_from_db()
        assert first_op.status == 'running'
        assert first_op.current_operator == operator.user
        first_op.work_order.refresh_from_db()
        assert first_op.work_order.status == 'in_progress'

    def test_pause_then_resume_then_stop_completes_op(self, operator, first_op):
        time_logging.record_event(operator, 'start_job', work_order_operation=first_op)
        time_logging.record_event(operator, 'pause_job', work_order_operation=first_op)
        first_op.refresh_from_db()
        assert first_op.status == 'paused'
        time_logging.record_event(operator, 'resume_job', work_order_operation=first_op)
        first_op.refresh_from_db()
        assert first_op.status == 'running'
        time_logging.record_event(operator, 'stop_job', work_order_operation=first_op)
        first_op.refresh_from_db()
        assert first_op.status == 'completed'
        assert first_op.completed_at is not None

    def test_stop_last_open_op_auto_completes_work_order(self, operator, work_order):
        ops = list(work_order.operations.order_by('sequence'))
        assert len(ops) == 2
        # Mark op 0 done first by directly setting status (skip the time-log path).
        MESWorkOrderOperation.objects.filter(pk=ops[0].pk).update(status='skipped')
        # Now run a full lifecycle on the last remaining op.
        time_logging.record_event(operator, 'start_job', work_order_operation=ops[1])
        time_logging.record_event(operator, 'stop_job', work_order_operation=ops[1])
        work_order.refresh_from_db()
        assert work_order.status == 'completed'
        assert work_order.completed_at is not None

    def test_clock_in_creates_log_without_op(self, operator):
        log = time_logging.record_event(operator, 'clock_in')
        assert log.action == 'clock_in'
        assert log.work_order_operation is None
        assert OperatorTimeLog.objects.count() == 1

    def test_actual_minutes_recomputed_after_each_event(self, operator, first_op):
        t0 = timezone.now() - timedelta(minutes=20)
        time_logging.record_event(operator, 'start_job', work_order_operation=first_op, now=t0)
        time_logging.record_event(
            operator, 'stop_job', work_order_operation=first_op,
            now=t0 + timedelta(minutes=15),
        )
        first_op.refresh_from_db()
        # Allow rounding tolerance
        assert Decimal('14.99') <= first_op.actual_minutes <= Decimal('15.01')


# ============================================================================
# Reporting — record_production + rollup_work_order
# ============================================================================

@pytest.mark.django_db
class TestRecordProduction:
    def test_happy_path_bumps_op_and_wo(self, first_op, acme_admin):
        rpt = reporting.record_production(
            first_op, good=Decimal('5'), scrap=Decimal('1'), rework=Decimal('0'),
            scrap_reason='material_defect', reported_by=acme_admin,
        )
        assert rpt.good_qty == Decimal('5')
        first_op.refresh_from_db()
        assert first_op.total_good_qty == Decimal('5')
        assert first_op.total_scrap_qty == Decimal('1')
        first_op.work_order.refresh_from_db()
        assert first_op.work_order.quantity_completed == Decimal('5')
        assert first_op.work_order.quantity_scrapped == Decimal('1')

    def test_negative_rejected(self, first_op, acme_admin):
        with pytest.raises(ValueError):
            reporting.record_production(
                first_op, good=Decimal('-1'), scrap=Decimal('0'), rework=Decimal('0'),
                reported_by=acme_admin,
            )

    def test_all_zero_rejected(self, first_op, acme_admin):
        with pytest.raises(ValueError):
            reporting.record_production(
                first_op, good=Decimal('0'), scrap=Decimal('0'), rework=Decimal('0'),
                reported_by=acme_admin,
            )

    def test_two_reports_accumulate(self, first_op, acme_admin):
        reporting.record_production(
            first_op, good=Decimal('3'), scrap=Decimal('0'), rework=Decimal('0'),
            reported_by=acme_admin,
        )
        reporting.record_production(
            first_op, good=Decimal('4'), scrap=Decimal('0'), rework=Decimal('0'),
            reported_by=acme_admin,
        )
        first_op.refresh_from_db()
        assert first_op.total_good_qty == Decimal('7')


@pytest.mark.django_db
class TestRollupWorkOrder:
    def test_empty_rollup(self, work_order):
        rollup = reporting.rollup_work_order(work_order)
        assert rollup['good'] == Decimal('0')
        assert rollup['scrap'] == Decimal('0')
        assert rollup['completed_pct'] == Decimal('0')

    def test_rollup_after_partial_report(self, work_order, first_op, acme_admin):
        # work_order quantity_to_build is 10
        reporting.record_production(
            first_op, good=Decimal('5'), scrap=Decimal('0'), rework=Decimal('0'),
            reported_by=acme_admin,
        )
        rollup = reporting.rollup_work_order(work_order)
        assert rollup['good'] == Decimal('5')
        assert rollup['completed_pct'] == Decimal('50.00')

    def test_rollup_capped_at_100(self, work_order, first_op, acme_admin):
        # report MORE than the target — pct must clamp to 100
        reporting.record_production(
            first_op, good=Decimal('20'), scrap=Decimal('0'), rework=Decimal('0'),
            reported_by=acme_admin,
        )
        rollup = reporting.rollup_work_order(work_order)
        assert rollup['completed_pct'] == Decimal('100.00')
