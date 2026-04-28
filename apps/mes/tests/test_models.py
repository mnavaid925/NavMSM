"""Unit tests on MES model invariants and status transition helpers."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.mes.models import (
    AndonAlert, MESWorkOrder, MESWorkOrderOperation, ShopFloorOperator,
    WorkInstruction, ProductionReport,
)


@pytest.mark.django_db
class TestWorkOrderTransitions:
    def test_dispatched_is_editable(self, work_order):
        assert work_order.is_editable() is True

    def test_in_progress_not_editable(self, work_order):
        work_order.status = 'in_progress'
        work_order.save()
        assert work_order.is_editable() is False

    def test_dispatched_can_start(self, work_order):
        assert work_order.can_start() is True

    def test_in_progress_cannot_start(self, work_order):
        work_order.status = 'in_progress'
        work_order.save()
        assert work_order.can_start() is False

    def test_in_progress_can_hold(self, work_order):
        work_order.status = 'in_progress'
        work_order.save()
        assert work_order.can_hold() is True

    def test_dispatched_cannot_complete(self, work_order):
        assert work_order.can_complete() is False

    def test_in_progress_can_complete(self, work_order):
        work_order.status = 'in_progress'
        work_order.save()
        assert work_order.can_complete() is True

    def test_completed_cannot_cancel(self, work_order):
        work_order.status = 'completed'
        work_order.save()
        assert work_order.can_cancel() is False

    def test_dispatched_can_cancel(self, work_order):
        assert work_order.can_cancel() is True


@pytest.mark.django_db
class TestOperationTransitions:
    def test_pending_can_start(self, first_op):
        assert first_op.can_start() is True

    def test_running_cannot_start_again(self, first_op):
        first_op.status = 'running'
        first_op.save()
        assert first_op.can_start() is False

    def test_running_can_pause(self, first_op):
        first_op.status = 'running'
        first_op.save()
        assert first_op.can_pause() is True

    def test_paused_can_resume(self, first_op):
        first_op.status = 'paused'
        first_op.save()
        assert first_op.can_resume() is True

    def test_running_can_stop(self, first_op):
        first_op.status = 'running'
        first_op.save()
        assert first_op.can_stop() is True

    def test_completed_cannot_stop(self, first_op):
        first_op.status = 'completed'
        first_op.save()
        assert first_op.can_stop() is False


@pytest.mark.django_db
class TestAndonTransitions:
    def test_open_can_acknowledge(self, open_andon):
        assert open_andon.can_acknowledge() is True

    def test_resolved_cannot_acknowledge(self, open_andon):
        open_andon.status = 'resolved'
        open_andon.save()
        assert open_andon.can_acknowledge() is False

    def test_acknowledged_can_resolve(self, open_andon):
        open_andon.status = 'acknowledged'
        open_andon.save()
        assert open_andon.can_resolve() is True

    def test_open_can_cancel(self, open_andon):
        assert open_andon.can_cancel() is True

    def test_cancelled_cannot_cancel(self, open_andon):
        open_andon.status = 'cancelled'
        open_andon.save()
        assert open_andon.can_cancel() is False


@pytest.mark.django_db
class TestWorkInstructionValidation:
    def test_clean_requires_routing_op_or_product(self, acme):
        wi = WorkInstruction(
            tenant=acme, instruction_number='SOP-X', title='X',
            doc_type='sop',
        )
        with pytest.raises(ValidationError):
            wi.clean()

    def test_clean_passes_with_product(self, acme, product):
        wi = WorkInstruction(
            tenant=acme, instruction_number='SOP-Y', title='Y',
            doc_type='sop', product=product,
        )
        wi.clean()  # should not raise

    def test_draft_is_editable(self, draft_instruction):
        assert draft_instruction.is_editable() is True

    def test_released_not_editable(self, draft_instruction):
        draft_instruction.status = 'released'
        draft_instruction.save()
        assert draft_instruction.is_editable() is False


# ---------------------------------------------------------------------------
# Decimal-validator regression (Lesson L-02)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestModelLevelBoundsL02:
    def test_negative_quantity_rejected_on_full_clean(self, acme, released_po, product):
        wo = MESWorkOrder(
            tenant=acme, wo_number='WO-X',
            production_order=released_po, product=product,
            quantity_to_build=Decimal('-1'),
        )
        with pytest.raises(ValidationError) as exc:
            wo.full_clean()
        assert 'quantity_to_build' in exc.value.error_dict

    def test_zero_quantity_rejected(self, acme, released_po, product):
        wo = MESWorkOrder(
            tenant=acme, wo_number='WO-X',
            production_order=released_po, product=product,
            quantity_to_build=Decimal('0'),
        )
        with pytest.raises(ValidationError):
            wo.full_clean()

    def test_negative_op_minutes_rejected(self, acme, work_order):
        op = MESWorkOrderOperation(
            tenant=acme, work_order=work_order,
            routing_operation=work_order.production_order.routing.operations.first(),
            sequence=99,
            operation_name='X',
            work_center=work_order.production_order.routing.operations.first().work_center,
            planned_minutes=Decimal('-5'),
        )
        with pytest.raises(ValidationError) as exc:
            op.full_clean()
        assert 'planned_minutes' in exc.value.error_dict

    def test_negative_good_qty_rejected_on_report(self, acme, first_op, acme_admin):
        from django.utils import timezone
        rpt = ProductionReport(
            tenant=acme, work_order_operation=first_op,
            good_qty=Decimal('-1'),
            scrap_qty=Decimal('0'), rework_qty=Decimal('0'),
            reported_by=acme_admin, reported_at=timezone.now(),
        )
        with pytest.raises(ValidationError):
            rpt.full_clean()


@pytest.mark.django_db
class TestUniqueConstraints:
    def test_wo_number_unique_per_tenant(self, acme, released_po, product):
        MESWorkOrder.objects.create(
            tenant=acme, wo_number='WO-DUP',
            production_order=released_po, product=product,
            quantity_to_build=Decimal('1'),
        )
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            MESWorkOrder.objects.create(
                tenant=acme, wo_number='WO-DUP',
                production_order=released_po, product=product,
                quantity_to_build=Decimal('2'),
            )

    def test_badge_number_unique_per_tenant(self, acme, acme_staff, work_center):
        ShopFloorOperator.objects.create(
            tenant=acme, user=acme_staff, badge_number='B-DUP',
            default_work_center=work_center,
        )
        # Different user, same badge → IntegrityError on unique_together
        from apps.accounts.models import User as U
        u2 = U.objects.create_user(username='u2', password='pw', tenant=acme)
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            ShopFloorOperator.objects.create(
                tenant=acme, user=u2, badge_number='B-DUP',
            )

    def test_op_sequence_unique_per_work_order(self, acme, work_order):
        rop = work_order.production_order.routing.operations.first()
        wc = rop.work_center
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            # First op already has sequence 10 from dispatch fan-out
            MESWorkOrderOperation.objects.create(
                tenant=acme, work_order=work_order,
                routing_operation=rop, sequence=10,
                operation_name='Dup', work_center=wc,
            )
