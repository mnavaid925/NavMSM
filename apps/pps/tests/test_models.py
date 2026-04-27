"""Unit tests on PPS model invariants — including D-04 numeric validators."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.pps.models import OptimizationObjective, RoutingOperation, WorkCenter


@pytest.mark.django_db
class TestMPSStatus:
    def test_draft_is_editable(self, draft_mps):
        assert draft_mps.is_editable() is True

    def test_released_is_not_editable(self, draft_mps):
        draft_mps.status = 'released'
        draft_mps.save()
        assert draft_mps.is_editable() is False


@pytest.mark.django_db
class TestProductionOrderTransitions:
    def test_planned_can_release(self, planned_order):
        assert planned_order.can_release() is True

    def test_released_cannot_release_again(self, planned_order):
        planned_order.status = 'released'
        planned_order.save()
        assert planned_order.can_release() is False

    def test_in_progress_can_complete(self, planned_order):
        planned_order.status = 'in_progress'
        planned_order.save()
        assert planned_order.can_complete() is True


@pytest.mark.django_db
class TestRoutingOperationMath:
    def test_total_minutes_setup_plus_run_plus_queue_plus_move(self, routing):
        op = routing.operations.order_by('sequence').first()
        # 15 setup + 5 * 10 run + 5 queue + 3 move = 73
        assert op.total_minutes(Decimal('10')) == Decimal('73')


# --- D-04 regression: model-level validators must reject out-of-range input.

@pytest.mark.django_db
class TestModelLevelBoundsD04:
    def test_negative_capacity_rejected(self, acme):
        wc = WorkCenter(
            tenant=acme, code='X', name='X', work_center_type='machine',
            capacity_per_hour=Decimal('-5'),
            efficiency_pct=Decimal('100'), cost_per_hour=Decimal('10'),
        )
        with pytest.raises(ValidationError) as exc:
            wc.full_clean()
        assert 'capacity_per_hour' in exc.value.error_dict

    def test_efficiency_above_100_rejected(self, acme):
        wc = WorkCenter(
            tenant=acme, code='X', name='X', work_center_type='machine',
            capacity_per_hour=Decimal('5'),
            efficiency_pct=Decimal('999'), cost_per_hour=Decimal('10'),
        )
        with pytest.raises(ValidationError) as exc:
            wc.full_clean()
        assert 'efficiency_pct' in exc.value.error_dict

    def test_negative_cost_rejected(self, acme):
        wc = WorkCenter(
            tenant=acme, code='X', name='X', work_center_type='machine',
            capacity_per_hour=Decimal('5'),
            efficiency_pct=Decimal('100'), cost_per_hour=Decimal('-1'),
        )
        with pytest.raises(ValidationError) as exc:
            wc.full_clean()
        assert 'cost_per_hour' in exc.value.error_dict

    def test_negative_run_minutes_rejected(self, acme, work_center, routing):
        op = RoutingOperation(
            tenant=acme, routing=routing, sequence=99, operation_name='X',
            work_center=work_center,
            setup_minutes=Decimal('0'),
            run_minutes_per_unit=Decimal('-5'),
            queue_minutes=Decimal('0'),
            move_minutes=Decimal('0'),
        )
        with pytest.raises(ValidationError) as exc:
            op.full_clean()
        assert 'run_minutes_per_unit' in exc.value.error_dict

    def test_zero_quantity_rejected(self, acme, planned_order):
        planned_order.quantity = Decimal('0')
        with pytest.raises(ValidationError) as exc:
            planned_order.full_clean()
        assert 'quantity' in exc.value.error_dict

    def test_negative_objective_weight_rejected(self, acme):
        obj = OptimizationObjective(
            tenant=acme, name='Bad',
            weight_changeovers=Decimal('-1'),
            weight_idle=Decimal('1'),
            weight_lateness=Decimal('1'),
            weight_priority=Decimal('1'),
        )
        with pytest.raises(ValidationError) as exc:
            obj.full_clean()
        assert 'weight_changeovers' in exc.value.error_dict
