"""End-to-end workflow tests across IQC, IPQC, FQC, NCR, Calibration."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.qms.models import (
    CalibrationRecord, CertificateOfAnalysis, CorrectiveAction,
    FinalInspection, IncomingInspection, MeasurementEquipment,
    NonConformanceReport, ProcessInspection,
)


# ---- IQC Workflow ----

@pytest.mark.django_db
class TestIQCWorkflow:
    def _create(self, acme, raw_product, iqc_plan):
        return IncomingInspection.objects.create(
            tenant=acme, inspection_number='IQC-W-1', product=raw_product,
            plan=iqc_plan, received_qty=Decimal('100'), status='pending',
            sample_size=20, accept_number=2, reject_number=3,
        )

    def test_pending_to_in_inspection(self, admin_client, acme, raw_product, iqc_plan):
        i = self._create(acme, raw_product, iqc_plan)
        r = admin_client.post(reverse('qms:iqc_inspection_start', args=[i.pk]))
        i.refresh_from_db()
        assert r.status_code == 302
        assert i.status == 'in_inspection'

    def test_in_inspection_to_accepted(self, admin_client, acme, raw_product, iqc_plan):
        i = self._create(acme, raw_product, iqc_plan)
        i.status = 'in_inspection'; i.save()
        admin_client.post(reverse('qms:iqc_inspection_accept', args=[i.pk]))
        i.refresh_from_db()
        assert i.status == 'accepted'

    def test_in_inspection_to_rejected(self, admin_client, acme, raw_product, iqc_plan):
        i = self._create(acme, raw_product, iqc_plan)
        i.status = 'in_inspection'; i.save()
        admin_client.post(reverse('qms:iqc_inspection_reject', args=[i.pk]))
        i.refresh_from_db()
        assert i.status == 'rejected'

    def test_pending_cannot_be_accepted_directly(self, admin_client, acme, raw_product, iqc_plan):
        # Skip transition - the conditional UPDATE rejects it (Lesson L-03)
        i = self._create(acme, raw_product, iqc_plan)
        admin_client.post(reverse('qms:iqc_inspection_accept', args=[i.pk]))
        i.refresh_from_db()
        assert i.status == 'pending'  # unchanged


# ---- FQC Workflow ----

@pytest.mark.django_db
class TestFQCWorkflow:
    def _create(self, acme, fqc_plan, status='pending'):
        return FinalInspection.objects.create(
            tenant=acme, inspection_number='FQC-W-1', plan=fqc_plan,
            quantity_tested=Decimal('100'), status=status,
        )

    def test_workflow_pending_to_passed(self, admin_client, acme, fqc_plan):
        i = self._create(acme, fqc_plan)
        admin_client.post(reverse('qms:fqc_inspection_start', args=[i.pk]))
        admin_client.post(reverse('qms:fqc_inspection_pass', args=[i.pk]))
        i.refresh_from_db()
        assert i.status == 'passed'

    def test_coa_generated_only_for_passed(self, admin_client, acme, fqc_plan):
        i = self._create(acme, fqc_plan, status='passed')
        admin_client.get(reverse('qms:coa_render', args=[i.pk]))
        coa = CertificateOfAnalysis.objects.filter(inspection=i).first()
        assert coa is not None
        assert coa.coa_number.startswith('COA-')

    def test_coa_blocked_when_failed(self, admin_client, acme, fqc_plan):
        i = self._create(acme, fqc_plan, status='failed')
        r = admin_client.get(reverse('qms:coa_render', args=[i.pk]))
        # Redirect back to detail with warning - no CoA created
        assert r.status_code == 302
        assert not CertificateOfAnalysis.objects.filter(inspection=i).exists()

    def test_coa_release_to_customer(self, admin_client, acme, fqc_plan):
        i = self._create(acme, fqc_plan, status='passed')
        admin_client.get(reverse('qms:coa_render', args=[i.pk]))
        admin_client.post(reverse('qms:coa_release', args=[i.pk]))
        coa = CertificateOfAnalysis.objects.get(inspection=i)
        assert coa.released_to_customer is True
        assert coa.released_at is not None


# ---- NCR Workflow ----

@pytest.mark.django_db
class TestNCRWorkflow:
    def test_full_lifecycle(self, admin_client, open_ncr):
        url = lambda name: reverse(f'qms:ncr_{name}', args=[open_ncr.pk])
        admin_client.post(url('investigate'))
        open_ncr.refresh_from_db()
        assert open_ncr.status == 'investigating'
        admin_client.post(url('await_capa'))
        open_ncr.refresh_from_db()
        assert open_ncr.status == 'awaiting_capa'
        admin_client.post(url('resolve'))
        open_ncr.refresh_from_db()
        assert open_ncr.status == 'resolved'
        admin_client.post(url('close'), {'resolution_summary': 'Done.'})
        open_ncr.refresh_from_db()
        assert open_ncr.status == 'closed'
        assert open_ncr.closed_by is not None
        assert open_ncr.closed_at is not None

    def test_close_blocks_without_summary(self, admin_client, open_ncr):
        # Drive to resolved first
        open_ncr.status = 'resolved'; open_ncr.save()
        admin_client.post(reverse('qms:ncr_close', args=[open_ncr.pk]),
                          {'resolution_summary': '   '})
        open_ncr.refresh_from_db()
        assert open_ncr.status == 'resolved'  # close rejected

    def test_cancel_from_open(self, admin_client, open_ncr):
        admin_client.post(reverse('qms:ncr_cancel', args=[open_ncr.pk]))
        open_ncr.refresh_from_db()
        assert open_ncr.status == 'cancelled'

    def test_corrective_action_create_and_complete(self, admin_client, open_ncr, acme_admin):
        admin_client.post(reverse('qms:ca_create', args=[open_ncr.pk]), {
            'sequence': 10, 'action_text': 'Fix it',
            'owner': acme_admin.pk,
            'effectiveness_verified': False, 'verification_notes': '',
        })
        ca = CorrectiveAction.objects.get(ncr=open_ncr)
        admin_client.post(reverse('qms:ca_complete', args=[ca.pk]))
        ca.refresh_from_db()
        assert ca.status == 'completed'
        assert ca.completed_at is not None


# ---- Calibration Workflow ----

@pytest.mark.django_db
class TestCalibrationWorkflow:
    def test_filing_calibration_updates_equipment_due(self, admin_client, acme, equipment):
        old_next_due = equipment.next_due_at
        cal_at = timezone.now()
        admin_client.post(reverse('qms:calibration_create'), {
            'equipment': equipment.pk,
            'calibrated_at': cal_at.strftime('%Y-%m-%dT%H:%M'),
            'external_lab_name': '', 'standard': '',
            'result': 'pass', 'next_due_at': '', 'notes': 'Good.',
        })
        equipment.refresh_from_db()
        # Lesson L-15 - next_due_at updated via post_save signal
        assert equipment.next_due_at != old_next_due
        assert equipment.next_due_at > cal_at
        assert CalibrationRecord.objects.filter(equipment=equipment).count() == 1

    def test_equipment_retire(self, admin_client, equipment):
        admin_client.post(reverse('qms:equipment_retire', args=[equipment.pk]))
        equipment.refresh_from_db()
        assert equipment.status == 'retired'
        assert equipment.is_active is False

    def test_equipment_with_calibration_history_protected_from_delete(
        self, admin_client, acme, equipment, acme_admin,
    ):
        """Lesson L-17: regulated audit-trail child models use PROTECT on the
        parent FK so a single click cannot wipe the calibration history.
        """
        CalibrationRecord.objects.create(
            tenant=acme, record_number='CAL-PROT-1',
            equipment=equipment, calibrated_at=timezone.now(),
            result='pass',
        )
        # Try to delete equipment - should fail with ProtectedError -> redirect + warning
        admin_client.post(reverse('qms:equipment_delete', args=[equipment.pk]))
        # Equipment must still exist, calibration record must still exist
        equipment.refresh_from_db()
        assert equipment.pk is not None
        assert CalibrationRecord.objects.filter(equipment=equipment).count() == 1
