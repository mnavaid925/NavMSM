"""End-to-end workflow tests using Django test client.

Covers: dispatch flow, work order start/hold/complete/cancel, operation
start/pause/resume/stop (via the operator terminal), andon
acknowledge/resolve/cancel, and the work-instruction release/obsolete/ack
lifecycle.
"""
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.mes.models import (
    AndonAlert, MESWorkOrder, MESWorkOrderOperation, OperatorTimeLog,
    ProductionReport, WorkInstruction, WorkInstructionAcknowledgement,
    WorkInstructionVersion,
)


# ============================================================================
# Dispatch from the PPS production order detail page
# ============================================================================

@pytest.mark.django_db
class TestDispatchView:
    def test_admin_dispatch_creates_work_order(self, admin_client, released_po):
        url = reverse('mes:dispatch', args=[released_po.pk])
        resp = admin_client.post(url)
        assert resp.status_code == 302
        wo = MESWorkOrder.objects.get(production_order=released_po)
        assert wo.wo_number.startswith('WO-')
        assert resp.url == reverse('mes:work_order_detail', args=[wo.pk])

    def test_non_admin_dispatch_blocked(self, staff_client, released_po):
        url = reverse('mes:dispatch', args=[released_po.pk])
        resp = staff_client.post(url, follow=True)
        # TenantAdminRequiredMixin redirects to dashboard
        assert MESWorkOrder.objects.filter(production_order=released_po).count() == 0

    def test_dispatch_planned_po_fails_gracefully(self, admin_client, planned_po):
        url = reverse('mes:dispatch', args=[planned_po.pk])
        resp = admin_client.post(url, follow=True)
        # Redirected back to PPS detail with error toast
        assert MESWorkOrder.objects.filter(production_order=planned_po).count() == 0

    def test_dispatch_idempotent_on_double_submit(self, admin_client, released_po):
        url = reverse('mes:dispatch', args=[released_po.pk])
        admin_client.post(url)
        admin_client.post(url)
        assert MESWorkOrder.objects.filter(production_order=released_po).count() == 1


# ============================================================================
# Work order workflow
# ============================================================================

@pytest.mark.django_db
class TestWorkOrderWorkflow:
    def test_start_dispatched_wo(self, admin_client, work_order):
        resp = admin_client.post(reverse('mes:work_order_start', args=[work_order.pk]))
        work_order.refresh_from_db()
        assert work_order.status == 'in_progress'

    def test_hold_in_progress_wo(self, admin_client, work_order):
        work_order.status = 'in_progress'
        work_order.save()
        admin_client.post(reverse('mes:work_order_hold', args=[work_order.pk]))
        work_order.refresh_from_db()
        assert work_order.status == 'on_hold'

    def test_complete_in_progress_wo(self, admin_client, acme_admin, work_order):
        work_order.status = 'in_progress'
        work_order.save()
        admin_client.post(reverse('mes:work_order_complete', args=[work_order.pk]))
        work_order.refresh_from_db()
        assert work_order.status == 'completed'
        assert work_order.completed_at is not None
        assert work_order.completed_by == acme_admin

    def test_cancel_dispatched_wo(self, admin_client, work_order):
        admin_client.post(reverse('mes:work_order_cancel', args=[work_order.pk]))
        work_order.refresh_from_db()
        assert work_order.status == 'cancelled'

    def test_cannot_complete_dispatched_wo(self, admin_client, work_order):
        admin_client.post(reverse('mes:work_order_complete', args=[work_order.pk]))
        work_order.refresh_from_db()
        # Status unchanged because conditional UPDATE rejects
        assert work_order.status == 'dispatched'

    def test_delete_in_progress_wo_blocked(self, admin_client, work_order):
        work_order.status = 'in_progress'
        work_order.save()
        admin_client.post(reverse('mes:work_order_delete', args=[work_order.pk]))
        # Still exists
        assert MESWorkOrder.objects.filter(pk=work_order.pk).exists()


# ============================================================================
# Operation workflow via terminal-style POSTs
# ============================================================================

@pytest.mark.django_db
class TestOperationWorkflow:
    def _login_as_operator(self, client, operator):
        client.force_login(operator.user)
        return client

    def test_start_op_records_log_and_promotes_wo(self, client, operator, first_op):
        c = self._login_as_operator(client, operator)
        c.post(reverse('mes:operation_start', args=[first_op.pk]))
        first_op.refresh_from_db()
        assert first_op.status == 'running'
        assert first_op.work_order.status == 'in_progress'
        assert OperatorTimeLog.objects.filter(
            operator=operator, action='start_job',
        ).count() == 1

    def test_pause_resume_stop_cycle(self, client, operator, first_op):
        c = self._login_as_operator(client, operator)
        c.post(reverse('mes:operation_start', args=[first_op.pk]))
        c.post(reverse('mes:operation_pause', args=[first_op.pk]))
        first_op.refresh_from_db()
        assert first_op.status == 'paused'
        c.post(reverse('mes:operation_resume', args=[first_op.pk]))
        first_op.refresh_from_db()
        assert first_op.status == 'running'
        c.post(reverse('mes:operation_stop', args=[first_op.pk]))
        first_op.refresh_from_db()
        assert first_op.status == 'completed'

    def test_op_start_without_operator_profile_blocked(
        self, admin_client, first_op,
    ):
        # admin_client logs in as acme_admin who has NO ShopFloorOperator row.
        admin_client.post(reverse('mes:operation_start', args=[first_op.pk]))
        first_op.refresh_from_db()
        # No state change because of the operator-profile check
        assert first_op.status == 'pending'
        assert OperatorTimeLog.objects.filter(work_order_operation=first_op).count() == 0


# ============================================================================
# Andon workflow
# ============================================================================

@pytest.mark.django_db
class TestAndonWorkflow:
    def test_acknowledge_open_andon(self, admin_client, open_andon, acme_admin):
        admin_client.post(reverse('mes:andon_acknowledge', args=[open_andon.pk]))
        open_andon.refresh_from_db()
        assert open_andon.status == 'acknowledged'
        assert open_andon.acknowledged_by == acme_admin
        assert open_andon.acknowledged_at is not None

    def test_resolve_with_notes(self, admin_client, open_andon, acme_admin):
        resp = admin_client.post(
            reverse('mes:andon_resolve', args=[open_andon.pk]),
            {'resolution_notes': 'Replaced cutting tool'},
        )
        open_andon.refresh_from_db()
        assert open_andon.status == 'resolved'
        assert open_andon.resolved_by == acme_admin
        assert 'Replaced cutting tool' in open_andon.resolution_notes

    def test_resolve_without_notes_rejected(self, admin_client, open_andon):
        admin_client.post(
            reverse('mes:andon_resolve', args=[open_andon.pk]),
            {'resolution_notes': ''},
        )
        open_andon.refresh_from_db()
        # Status NOT changed because form invalid
        assert open_andon.status == 'open'

    def test_cancel_open_andon_admin_only(self, admin_client, open_andon):
        admin_client.post(reverse('mes:andon_cancel', args=[open_andon.pk]))
        open_andon.refresh_from_db()
        assert open_andon.status == 'cancelled'

    def test_create_andon_assigns_alert_number(self, admin_client, work_center):
        resp = admin_client.post(
            reverse('mes:andon_create'),
            {
                'alert_type': 'quality', 'severity': 'high',
                'title': 'New defect', 'message': 'Visible on output.',
                'work_center': work_center.pk,
            },
        )
        assert AndonAlert.objects.filter(title='New defect').exists()
        a = AndonAlert.objects.get(title='New defect')
        assert a.alert_number.startswith('AND-')
        assert a.raised_at is not None


# ============================================================================
# Work-instruction lifecycle
# ============================================================================

@pytest.mark.django_db
class TestInstructionWorkflow:
    def test_release_version_supersedes_prior(
        self, admin_client, draft_instruction, draft_instruction_version, acme_admin,
    ):
        # Release v1.0
        admin_client.post(reverse(
            'mes:instruction_version_release', args=[draft_instruction_version.pk],
        ))
        draft_instruction.refresh_from_db()
        draft_instruction_version.refresh_from_db()
        assert draft_instruction_version.status == 'released'
        assert draft_instruction.current_version_id == draft_instruction_version.pk
        assert draft_instruction.status == 'released'

        # Add v1.1, release it
        v2 = WorkInstructionVersion.objects.create(
            tenant=draft_instruction.tenant, instruction=draft_instruction,
            version='1.1', content='updated', status='draft',
            uploaded_by=acme_admin,
        )
        admin_client.post(reverse('mes:instruction_version_release', args=[v2.pk]))
        v2.refresh_from_db()
        draft_instruction_version.refresh_from_db()
        draft_instruction.refresh_from_db()
        assert v2.status == 'released'
        # Prior released version auto-obsoleted
        assert draft_instruction_version.status == 'obsolete'
        assert draft_instruction.current_version_id == v2.pk

    def test_obsolete_current_version_clears_pointer(
        self, admin_client, draft_instruction, draft_instruction_version,
    ):
        admin_client.post(reverse(
            'mes:instruction_version_release', args=[draft_instruction_version.pk],
        ))
        admin_client.post(reverse(
            'mes:instruction_version_obsolete', args=[draft_instruction_version.pk],
        ))
        draft_instruction.refresh_from_db()
        assert draft_instruction.current_version is None
        assert draft_instruction.status == 'obsolete'

    def test_acknowledge_typed_signature(
        self, admin_client, draft_instruction, draft_instruction_version, acme_admin,
    ):
        admin_client.post(reverse(
            'mes:instruction_version_release', args=[draft_instruction_version.pk],
        ))
        admin_client.post(
            reverse('mes:instruction_acknowledge', args=[draft_instruction.pk]),
            {'signature_text': 'Test User'},
        )
        ack = WorkInstructionAcknowledgement.objects.get(
            instruction=draft_instruction, user=acme_admin,
        )
        assert ack.signature_text == 'Test User'
        assert ack.instruction_version == '1.0'

    def test_acknowledge_blank_signature_rejected(
        self, admin_client, draft_instruction, draft_instruction_version,
    ):
        admin_client.post(reverse(
            'mes:instruction_version_release', args=[draft_instruction_version.pk],
        ))
        admin_client.post(
            reverse('mes:instruction_acknowledge', args=[draft_instruction.pk]),
            {'signature_text': '   '},
        )
        assert WorkInstructionAcknowledgement.objects.filter(
            instruction=draft_instruction,
        ).count() == 0

    def test_duplicate_acknowledgement_idempotent(
        self, admin_client, draft_instruction, draft_instruction_version, acme_admin,
    ):
        admin_client.post(reverse(
            'mes:instruction_version_release', args=[draft_instruction_version.pk],
        ))
        for _ in range(2):
            admin_client.post(
                reverse('mes:instruction_acknowledge', args=[draft_instruction.pk]),
                {'signature_text': 'Test User'},
            )
        # unique_together rejects the dup
        assert WorkInstructionAcknowledgement.objects.filter(
            instruction=draft_instruction, user=acme_admin,
        ).count() == 1


# ============================================================================
# Production report endpoint
# ============================================================================

@pytest.mark.django_db
class TestReportCreateView:
    def test_post_filed_report_bumps_op_and_wo(
        self, admin_client, first_op, work_order,
    ):
        admin_client.post(
            reverse('mes:report_create'),
            {
                'work_order_operation': first_op.pk,
                'good_qty': '7', 'scrap_qty': '0', 'rework_qty': '0',
                'scrap_reason': '', 'cycle_time_minutes': '', 'notes': '',
            },
        )
        first_op.refresh_from_db()
        assert first_op.total_good_qty == Decimal('7')
        work_order.refresh_from_db()
        assert work_order.quantity_completed == Decimal('7')

    def test_delete_report_adjusts_denorms(
        self, admin_client, first_op, work_order, acme_admin,
    ):
        from apps.mes.services import reporting
        rpt = reporting.record_production(
            first_op, good=Decimal('4'), scrap=Decimal('0'), rework=Decimal('0'),
            reported_by=acme_admin,
        )
        admin_client.post(reverse('mes:report_delete', args=[rpt.pk]))
        first_op.refresh_from_db()
        work_order.refresh_from_db()
        assert first_op.total_good_qty == Decimal('0')
        assert work_order.quantity_completed == Decimal('0')
