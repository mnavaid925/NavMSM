"""Audit-log signal tests + Lesson L-15 calibration -> equipment propagation."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.tenants.models import TenantAuditLog
from apps.qms.models import (
    CalibrationRecord, CertificateOfAnalysis, CorrectiveAction,
    FinalInspection, IncomingInspection, MeasurementEquipment,
    NonConformanceReport, ProcessInspection,
)


@pytest.mark.django_db
class TestAuditLogEmission:
    def _audit(self, tenant, action_prefix):
        return TenantAuditLog.objects.filter(
            tenant=tenant, action__startswith=action_prefix,
        )

    def test_iqc_inspection_creation_emits_audit(self, acme, raw_product, iqc_plan):
        IncomingInspection.objects.create(
            tenant=acme, inspection_number='IQC-A', product=raw_product,
            plan=iqc_plan, received_qty=Decimal('100'),
        )
        assert self._audit(acme, 'qms_iqc.created').exists()

    def test_iqc_status_transition_emits_audit(self, acme, raw_product, iqc_plan):
        i = IncomingInspection.objects.create(
            tenant=acme, inspection_number='IQC-B', product=raw_product,
            plan=iqc_plan, received_qty=Decimal('100'), status='pending',
        )
        i.status = 'in_inspection'
        i.save()
        assert self._audit(acme, 'qms_iqc.in_inspection').exists()

    def test_ncr_creation_emits_audit(self, acme, fg_product, acme_admin):
        NonConformanceReport.objects.create(
            tenant=acme, ncr_number='NCR-A', source='fqc', severity='critical',
            title='Test', product=fg_product, lot_number='L1',
            quantity_affected=Decimal('1'),
            reported_by=acme_admin, reported_at=timezone.now(),
        )
        assert self._audit(acme, 'qms_ncr.created').exists()

    def test_ncr_close_emits_audit(self, open_ncr, acme):
        open_ncr.status = 'closed'
        open_ncr.save()
        assert self._audit(acme, 'qms_ncr.closed').exists()

    def test_corrective_action_completion_emits_audit(self, open_ncr, acme, acme_admin):
        ca = CorrectiveAction.objects.create(
            tenant=acme, ncr=open_ncr, sequence=10,
            action_text='do thing', owner=acme_admin, status='open',
        )
        ca.status = 'completed'
        ca.save()
        assert self._audit(acme, 'qms_ca.completed').exists()


@pytest.mark.django_db
class TestL15CalibrationPropagation:
    """Filing a CalibrationRecord must update equipment.last_calibrated_at +
    next_due_at via the post_save signal (Lesson L-15: capture local first)."""

    def test_calibration_updates_equipment_last_calibrated(self, acme, equipment):
        cal_at = timezone.now()
        CalibrationRecord.objects.create(
            tenant=acme, record_number='CAL-A', equipment=equipment,
            calibrated_at=cal_at, result='pass',
        )
        equipment.refresh_from_db()
        # Equipment.last_calibrated_at should match
        assert equipment.last_calibrated_at is not None
        assert abs((equipment.last_calibrated_at - cal_at).total_seconds()) < 5

    def test_calibration_sets_next_due_when_explicit(self, acme, equipment):
        cal_at = timezone.now()
        next_due = cal_at + timedelta(days=180)
        CalibrationRecord.objects.create(
            tenant=acme, record_number='CAL-B', equipment=equipment,
            calibrated_at=cal_at, next_due_at=next_due, result='pass',
        )
        equipment.refresh_from_db()
        assert abs((equipment.next_due_at - next_due).total_seconds()) < 5

    def test_calibration_computes_next_due_when_missing(self, acme, equipment):
        cal_at = timezone.now()
        CalibrationRecord.objects.create(
            tenant=acme, record_number='CAL-C', equipment=equipment,
            calibrated_at=cal_at, result='pass',
            # no next_due_at provided
        )
        equipment.refresh_from_db()
        # Signal should compute cal_at + interval_days
        expected = cal_at + timedelta(days=equipment.calibration_interval_days)
        assert abs((equipment.next_due_at - expected).total_seconds()) < 5

    def test_calibration_creation_emits_audit(self, acme, equipment):
        CalibrationRecord.objects.create(
            tenant=acme, record_number='CAL-AU', equipment=equipment,
            calibrated_at=timezone.now(), result='pass',
        )
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='qms_calibration.created',
        ).exists()
