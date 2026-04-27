"""Audit-log emission tests — D-11 regression coverage."""
from decimal import Decimal

import pytest

from apps.tenants.models import TenantAuditLog


@pytest.mark.django_db
class TestConfigAuditCoverageD11:
    def test_workcenter_create_emits_audit(self, acme, work_center):
        # Fixture creates a WorkCenter -> expect work_center.created entry.
        entries = TenantAuditLog.objects.filter(
            tenant=acme, action='work_center.created',
            target_id=str(work_center.pk),
        )
        assert entries.exists()

    def test_workcenter_update_emits_audit(self, acme, work_center):
        TenantAuditLog.objects.filter(tenant=acme).delete()
        work_center.cost_per_hour = Decimal('99')
        work_center.save()
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='work_center.updated',
            target_id=str(work_center.pk),
        ).exists()

    def test_workcenter_delete_emits_audit(self, acme, work_center):
        wc_pk = str(work_center.pk)
        TenantAuditLog.objects.filter(tenant=acme).delete()
        work_center.delete()
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='work_center.deleted', target_id=wc_pk,
        ).exists()

    def test_routing_create_emits_audit(self, acme, routing):
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='routing.created',
            target_id=str(routing.pk),
        ).exists()

    def test_routing_operation_create_emits_audit(self, acme, routing):
        # Fixture's RoutingOperations also emit audit entries.
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='routing_operation.created',
        ).exists()

    def test_capacity_calendar_create_emits_audit(self, acme, work_center):
        # Fixture creates 5 weekday calendars.
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='capacity_calendar.created',
        ).exists()
