"""Audit-log signal tests.

Validate that every state-changing MES operation writes a corresponding
``apps.tenants.TenantAuditLog`` entry. Mirrors the PPS / MRP audit-log test
pattern.
"""
from decimal import Decimal

import pytest

from apps.mes.models import (
    AndonAlert, MESWorkOrder, MESWorkOrderOperation, WorkInstruction,
    WorkInstructionVersion,
)
from apps.tenants.models import TenantAuditLog


@pytest.mark.django_db
class TestWorkOrderAuditLogs:
    def test_creation_logs_created(self, work_order):
        # work_order fixture invokes the dispatcher service, which creates the
        # WO via .create() — the post_save signal fires.
        assert TenantAuditLog.objects.filter(
            tenant=work_order.tenant, action='mes_work_order.created',
        ).exists()

    def test_status_transition_logs_target_state(self, work_order):
        work_order.status = 'in_progress'
        work_order.save()
        assert TenantAuditLog.objects.filter(
            tenant=work_order.tenant, action='mes_work_order.in_progress',
        ).exists()

    def test_status_meta_carries_from_to(self, work_order):
        work_order.status = 'in_progress'
        work_order.save()
        log = TenantAuditLog.objects.get(
            tenant=work_order.tenant, action='mes_work_order.in_progress',
        )
        assert log.meta.get('from') == 'dispatched'
        assert log.meta.get('to') == 'in_progress'

    def test_no_log_on_non_status_save(self, work_order):
        TenantAuditLog.objects.filter(tenant=work_order.tenant).delete()
        work_order.notes = 'just a note edit'
        work_order.save()
        # No transition log written
        assert not TenantAuditLog.objects.filter(
            tenant=work_order.tenant, action__startswith='mes_work_order.',
        ).exists()


@pytest.mark.django_db
class TestOperationAuditLogs:
    def test_create_does_not_log(self, work_order):
        # Operations are seeded via dispatch — they should NOT emit per-create
        # audit entries (high-frequency model).
        assert not TenantAuditLog.objects.filter(
            tenant=work_order.tenant, target_type='MESWorkOrderOperation',
        ).exists()

    def test_op_running_logged(self, work_order):
        op = work_order.operations.first()
        op.status = 'running'
        op.save()
        assert TenantAuditLog.objects.filter(
            tenant=work_order.tenant, action='mes_op.running',
        ).exists()

    def test_op_pending_to_setup_not_logged(self, work_order):
        # Only 'running / paused / completed / skipped' transitions are logged.
        op = work_order.operations.first()
        op.status = 'setup'
        op.save()
        assert not TenantAuditLog.objects.filter(
            tenant=work_order.tenant, action='mes_op.setup',
        ).exists()


@pytest.mark.django_db
class TestAndonAuditLogs:
    def test_create_logs_created(self, open_andon):
        assert TenantAuditLog.objects.filter(
            tenant=open_andon.tenant, action='andon.created',
        ).exists()

    def test_acknowledge_logged(self, open_andon, acme_admin):
        from django.utils import timezone
        open_andon.status = 'acknowledged'
        open_andon.acknowledged_by = acme_admin
        open_andon.acknowledged_at = timezone.now()
        open_andon.save()
        assert TenantAuditLog.objects.filter(
            tenant=open_andon.tenant, action='andon.acknowledged',
        ).exists()

    def test_resolve_logged(self, open_andon, acme_admin):
        from django.utils import timezone
        open_andon.status = 'resolved'
        open_andon.resolved_by = acme_admin
        open_andon.resolved_at = timezone.now()
        open_andon.resolution_notes = 'fixed'
        open_andon.save()
        assert TenantAuditLog.objects.filter(
            tenant=open_andon.tenant, action='andon.resolved',
        ).exists()


@pytest.mark.django_db
class TestWorkInstructionAuditLogs:
    def test_creation_logs_created(self, draft_instruction):
        assert TenantAuditLog.objects.filter(
            tenant=draft_instruction.tenant, action='work_instruction.created',
        ).exists()

    def test_release_logged(self, draft_instruction):
        draft_instruction.status = 'released'
        draft_instruction.save()
        assert TenantAuditLog.objects.filter(
            tenant=draft_instruction.tenant, action='work_instruction.released',
        ).exists()

    def test_version_release_logged(self, draft_instruction_version):
        draft_instruction_version.status = 'released'
        draft_instruction_version.save()
        assert TenantAuditLog.objects.filter(
            tenant=draft_instruction_version.tenant,
            action='work_instruction_version.released',
        ).exists()

    def test_version_obsolete_logged(self, draft_instruction_version):
        draft_instruction_version.status = 'obsolete'
        draft_instruction_version.save()
        assert TenantAuditLog.objects.filter(
            tenant=draft_instruction_version.tenant,
            action='work_instruction_version.obsolete',
        ).exists()


@pytest.mark.django_db
class TestAcknowledgementVersionSnapshot:
    """The pre_save signal must snapshot the version string."""

    def test_snapshot_filled_when_blank(
        self, acme, draft_instruction, draft_instruction_version, acme_admin,
    ):
        from apps.mes.models import WorkInstructionAcknowledgement
        # Promote the version to released + set current_version
        draft_instruction_version.status = 'released'
        draft_instruction_version.save()
        draft_instruction.current_version = draft_instruction_version
        draft_instruction.status = 'released'
        draft_instruction.save()

        # Create an ack with NO instruction_version supplied
        ack = WorkInstructionAcknowledgement.objects.create(
            tenant=acme, instruction=draft_instruction,
            user=acme_admin, signature_text='Tester',
        )
        # Signal should have stamped it from the current version
        assert ack.instruction_version == '1.0'
