"""Audit-log emission tests for MRP signals.

Covers:
- post_save status transitions (mrp_run.created, mrp_calculation.status.X, mrp_pr.X, mrp_exception.X)
- post_delete (F-11 / D-10): destructive ops emit audit rows.
"""
from datetime import date, timedelta

import pytest

from apps.tenants.models import TenantAuditLog
from apps.mrp.models import (
    MRPCalculation, MRPException, MRPPurchaseRequisition, MRPRun,
)


@pytest.mark.django_db
class TestRunAudit:
    def test_run_create_emits_audit(self, acme, calc):
        TenantAuditLog.objects.filter(tenant=acme).delete()
        run = MRPRun.objects.create(
            tenant=acme, run_number='MRPRUN-A1', name='a',
            run_type='regenerative', status='queued', mrp_calculation=calc,
        )
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='mrp_run.created', target_id=str(run.pk),
        ).exists()

    def test_run_status_change_emits_audit(self, acme, calc):
        run = MRPRun.objects.create(
            tenant=acme, run_number='MRPRUN-A2', name='a',
            run_type='regenerative', status='queued', mrp_calculation=calc,
        )
        TenantAuditLog.objects.filter(tenant=acme).delete()
        run.status = 'running'
        run.save()
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='mrp_run.running', target_id=str(run.pk),
        ).exists()

    def test_run_delete_emits_audit_d10(self, acme, calc):
        """F-11 / D-10: destructive ops on MRPRun must leave an audit trail."""
        run = MRPRun.objects.create(
            tenant=acme, run_number='MRPRUN-A3', name='a',
            run_type='regenerative', status='completed', mrp_calculation=calc,
        )
        run_pk = str(run.pk)
        TenantAuditLog.objects.filter(tenant=acme).delete()
        run.delete()
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='mrp_run.deleted', target_id=run_pk,
        ).exists()


@pytest.mark.django_db
class TestCalcAudit:
    def test_calc_create_emits_audit(self, acme, calc):
        # The calc fixture itself fires post_save; just verify it's there.
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='mrp_calculation.created', target_id=str(calc.pk),
        ).exists()

    def test_calc_status_change_emits_audit(self, acme, calc):
        TenantAuditLog.objects.filter(tenant=acme).delete()
        calc.status = 'completed'
        calc.save()
        assert TenantAuditLog.objects.filter(
            tenant=acme,
            action='mrp_calculation.status.completed',
            target_id=str(calc.pk),
        ).exists()

    def test_calc_delete_emits_audit_d10(self, acme, acme_admin):
        """F-11 / D-10: deleting a calculation must leave an audit trail."""
        c = MRPCalculation.objects.create(
            tenant=acme, mrp_number='MRP-DEL', name='to delete',
            horizon_start=date.today(), horizon_end=date.today() + timedelta(days=7),
            time_bucket='week', status='draft', started_by=acme_admin,
        )
        c_pk = str(c.pk)
        TenantAuditLog.objects.filter(tenant=acme).delete()
        c.delete()
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='mrp_calculation.deleted', target_id=c_pk,
        ).exists()


@pytest.mark.django_db
class TestPRAudit:
    def test_pr_approve_emits_audit(self, acme, calc, raw_product, make_pr):
        pr = make_pr(acme, calc, raw_product)
        TenantAuditLog.objects.filter(tenant=acme).delete()
        pr.status = 'approved'
        pr.save()
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='mrp_pr.approved', target_id=str(pr.pk),
        ).exists()

    def test_pr_delete_emits_audit_d10(self, acme, calc, raw_product, make_pr):
        pr = make_pr(acme, calc, raw_product)
        pr_pk = str(pr.pk)
        TenantAuditLog.objects.filter(tenant=acme).delete()
        pr.delete()
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='mrp_pr.deleted', target_id=pr_pk,
        ).exists()


@pytest.mark.django_db
class TestExceptionAudit:
    def test_exc_resolve_emits_audit(self, acme, calc, raw_product):
        exc = MRPException.objects.create(
            tenant=acme, mrp_calculation=calc, product=raw_product,
            exception_type='late_order', severity='high', message='m',
        )
        TenantAuditLog.objects.filter(tenant=acme).delete()
        exc.status = 'resolved'
        exc.save()
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='mrp_exception.resolved', target_id=str(exc.pk),
        ).exists()

    def test_exc_delete_emits_audit_d10(self, acme, calc, raw_product):
        exc = MRPException.objects.create(
            tenant=acme, mrp_calculation=calc, product=raw_product,
            exception_type='late_order', severity='high', message='m',
            status='resolved',
        )
        exc_pk = str(exc.pk)
        TenantAuditLog.objects.filter(tenant=acme).delete()
        exc.delete()
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='mrp_exception.deleted', target_id=exc_pk,
        ).exists()
