"""Regression tests for the bugs surfaced during the manual-test walk-through.

Each test ties to a numbered bug from
`.claude/manual-tests/mes-manual-test.md` §5 Bug Log.
"""
from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant
from apps.mes.management.commands.seed_mes import (
    _seed_operators, _seed_time_logs_and_reports, _seed_work_orders,
)
from apps.mes.models import (
    MESWorkOrder, MESWorkOrderOperation, OperatorTimeLog, ProductionReport,
    ShopFloorOperator,
)
from apps.pps.models import ProductionOrder


# ============================================================================
# BUG-01 — ASCII-only stdout (Lesson L-09)
# ============================================================================

@pytest.mark.django_db
class TestBug01AsciiSafeStdout:
    def test_seeder_stdout_is_ascii_only(
        self, acme, acme_admin, released_po, work_center,
    ):
        """The seeder's stdout output must contain only ASCII characters,
        otherwise it crashes on Windows cp1252 consoles (Lesson L-09).
        """
        # Need a non-admin user to receive an operator profile so the time-log
        # path is exercised.
        User.objects.create_user(
            username='staff_t', password='pw', tenant=acme, is_tenant_admin=False,
        )
        out = StringIO()
        operators = _seed_operators(acme, out)
        work_orders = _seed_work_orders(acme, acme_admin, out)
        # Promote one work order to in_progress so the report path runs.
        if work_orders:
            MESWorkOrder.all_objects.filter(pk=work_orders[0].pk).update(
                status='in_progress',
            )
            work_orders = list(MESWorkOrder.all_objects.filter(tenant=acme))
        _seed_time_logs_and_reports(acme, work_orders, operators, acme_admin, out)
        text = out.getvalue()
        # encode -> ascii must succeed without raising UnicodeEncodeError.
        text.encode('ascii')


# ============================================================================
# BUG-02 + BUG-03 — Seeded WO rollup must match seeded ProductionReport
# ============================================================================

@pytest.mark.django_db
class TestBug02SeededRollupConsistency:
    """
    BUG-02: completed seeded WO had quantity_completed=0 because the seeder
    read first_op.total_good_qty from a stale Python variable instead of the
    DB.
    BUG-03: in-progress seeded op had total_good_qty=0 while the seeded
    report said good_qty=5 (denorm did not match the report).
    Fix: seeder now uses one local variable for the value and writes it to
    the report, the op denorm, AND the work-order rollup.
    """

    def test_in_progress_op_denorms_match_report(
        self, acme, acme_admin, released_po, work_center,
    ):
        # Seed prerequisites
        staff = User.objects.create_user(
            username='staff_t2', password='pw', tenant=acme,
        )
        out = StringIO()
        operators = _seed_operators(acme, out)
        work_orders = _seed_work_orders(acme, acme_admin, out)
        # Force one WO to in_progress so the in-progress branch runs.
        wo = work_orders[0]
        MESWorkOrder.all_objects.filter(pk=wo.pk).update(status='in_progress')
        wo.refresh_from_db()
        _seed_time_logs_and_reports(
            acme, [wo], operators, acme_admin, out,
        )
        # The seeded report should match the op's total_good_qty
        first_op = wo.operations.order_by('sequence').first()
        first_op.refresh_from_db()
        rpt = ProductionReport.objects.filter(work_order_operation=first_op).first()
        assert rpt is not None
        assert rpt.good_qty == first_op.total_good_qty

    def test_completed_wo_rollup_reflects_report_quantity(
        self, acme, acme_admin, released_po,
    ):
        staff = User.objects.create_user(
            username='staff_t3', password='pw', tenant=acme,
        )
        out = StringIO()
        operators = _seed_operators(acme, out)
        work_orders = _seed_work_orders(acme, acme_admin, out)
        wo = work_orders[0]
        MESWorkOrder.all_objects.filter(pk=wo.pk).update(
            status='completed',
            completed_at=timezone.now(),
            completed_by=acme_admin,
        )
        wo.refresh_from_db()
        _seed_time_logs_and_reports(acme, [wo], operators, acme_admin, out)
        wo.refresh_from_db()
        first_op = wo.operations.order_by('sequence').first()
        first_op.refresh_from_db()
        # All three must match (BUG-02 had wo.quantity_completed=0).
        assert wo.quantity_completed == first_op.total_good_qty == wo.quantity_to_build


# ============================================================================
# BUG-04 — Routing-None branch must restore PO status
# ============================================================================

@pytest.mark.django_db
class TestBug04RoutingNoneRestoresStatus:
    def test_status_restored_when_routing_missing(
        self, acme, acme_admin, product,
    ):
        """A PO that was bumped from in_progress -> released for the dispatch
        attempt must be restored to in_progress when the routing is missing.
        """
        po_no_routing = ProductionOrder.objects.create(
            tenant=acme, order_number='PO-NOROUTE',
            product=product, routing=None,
            quantity=Decimal('1'),
            status='in_progress', priority='normal',
            scheduling_method='forward',
        )
        out = StringIO()
        _seed_work_orders(acme, acme_admin, out)
        po_no_routing.refresh_from_db()
        assert po_no_routing.status == 'in_progress', (
            'Seeder should restore the original PO status when routing is missing.'
        )


# ============================================================================
# BUG-05 — AndonResolveForm requires a non-empty resolution note
# ============================================================================

@pytest.mark.django_db
class TestBug05AndonResolveRequiresNotes:
    def test_blank_resolution_notes_rejected(self):
        from apps.mes.forms import AndonResolveForm
        form = AndonResolveForm(data={'resolution_notes': '   '})
        assert not form.is_valid()
        assert 'resolution_notes' in form.errors

    def test_non_empty_notes_accepted(self):
        from apps.mes.forms import AndonResolveForm
        form = AndonResolveForm(data={'resolution_notes': 'Replaced cutting tool'})
        assert form.is_valid()


# ============================================================================
# BUG-06 — InstructionAcknowledgeView wraps the create in a savepoint
# ============================================================================

@pytest.mark.django_db
class TestBug06AckSavepoint:
    def test_double_ack_does_not_break_test_transaction(
        self, admin_client, draft_instruction, draft_instruction_version, acme_admin,
    ):
        """If the IntegrityError on duplicate ack is not wrapped in a
        savepoint, it poisons the surrounding pytest transaction and
        downstream queries crash with TransactionManagementError.
        """
        from django.urls import reverse
        admin_client.post(reverse(
            'mes:instruction_version_release', args=[draft_instruction_version.pk],
        ))
        for _ in range(2):
            admin_client.post(
                reverse('mes:instruction_acknowledge', args=[draft_instruction.pk]),
                {'signature_text': 'Tester'},
            )
        # If the bug returns, this query raises TransactionManagementError.
        from apps.mes.models import WorkInstructionAcknowledgement
        assert WorkInstructionAcknowledgement.objects.filter(
            instruction=draft_instruction, user=acme_admin,
        ).count() == 1


# ============================================================================
# Smoke — full seed_mes orchestrated run does not crash
# ============================================================================

@pytest.mark.django_db
class TestSeederSmoke:
    def test_seed_mes_runs_to_completion(self, acme, acme_admin, released_po):
        """End-to-end: the seeder should complete with no exceptions even
        when only one tenant has any seeded prerequisite data.
        """
        # Need a non-admin staff user so _seed_operators picks them up.
        User.objects.create_user(
            username='staff_smoke', password='pw', tenant=acme,
            is_tenant_admin=False,
        )
        out = StringIO()
        call_command('seed_mes', stdout=out)
        text = out.getvalue()
        # Must be ASCII-only
        text.encode('ascii')
        # And must report at least one tenant header.
        assert '-> Tenant:' in text
