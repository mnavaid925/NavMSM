"""Form validation tests - L-01 unique_together, L-02 bounds, L-14 per-workflow."""
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.qms.forms import (
    CalibrationRecordForm, IncomingInspectionPlanForm, MeasurementEquipmentForm,
    NCRAttachmentForm, NCRCloseForm, ProcessInspectionPlanForm,
)


@pytest.mark.django_db
class TestL01UniqueTogetherInForms:
    """Forms whose Meta.fields excludes ``tenant`` must do their own uniqueness check."""

    def test_iqc_plan_form_rejects_duplicate_version_in_tenant(self, acme, raw_product, iqc_plan):
        f = IncomingInspectionPlanForm({
            'product': raw_product.pk, 'aql_level': 'II', 'sample_method': 'single',
            'aql_value': '2.5', 'version': iqc_plan.version, 'is_active': True,
        }, tenant=acme)
        assert not f.is_valid()
        assert 'version' in f.errors

    def test_iqc_plan_form_allows_dup_in_other_tenant(self, acme, globex, raw_product, globex_product, iqc_plan):
        # Same version label, different tenant -> should be fine
        f = IncomingInspectionPlanForm({
            'product': globex_product.pk, 'aql_level': 'II', 'sample_method': 'single',
            'aql_value': '2.5', 'version': iqc_plan.version, 'is_active': True,
        }, tenant=globex)
        # Edit the queryset since globex_product needs to be visible
        f.fields['product'].queryset = type(globex_product)._default_manager.filter(tenant=globex)
        assert f.is_valid(), f.errors

    def test_equipment_form_rejects_duplicate_serial(self, acme, equipment):
        f = MeasurementEquipmentForm({
            'name': 'Other', 'equipment_type': 'caliper',
            'serial_number': equipment.serial_number,
            'manufacturer': '', 'model_number': '',
            'range_min': '', 'range_max': '', 'unit_of_measure': '',
            'tolerance': '', 'calibration_interval_days': 365,
            'status': 'active', 'is_active': True, 'notes': '',
        }, tenant=acme)
        assert not f.is_valid()
        assert 'serial_number' in f.errors

    def test_ipqc_plan_form_rejects_dup_product_op_pair(self, acme, fg_product, routing_operation, ipqc_plan):
        f = ProcessInspectionPlanForm({
            'product': fg_product.pk,
            'routing_operation': routing_operation.pk,
            'name': 'duplicate', 'frequency': 'every_part', 'frequency_value': 1,
            'chart_type': 'none', 'subgroup_size': 5,
            'is_active': True,
        }, tenant=acme)
        assert not f.is_valid()
        assert 'routing_operation' in f.errors


@pytest.mark.django_db
class TestL14PerWorkflowRequiredFields:
    def test_ncr_close_requires_resolution_summary(self, open_ncr):
        f = NCRCloseForm({'resolution_summary': '   '}, instance=open_ncr)
        assert not f.is_valid()
        assert 'resolution_summary' in f.errors

    def test_ncr_close_accepts_real_summary(self, open_ncr):
        f = NCRCloseForm({'resolution_summary': 'Issue resolved.'}, instance=open_ncr)
        assert f.is_valid()

    def test_calibration_record_fail_without_notes_rejected(self, acme, equipment):
        f = CalibrationRecordForm({
            'calibrated_at': '2026-04-30T10:00',
            'external_lab_name': '',
            'result': 'fail', 'next_due_at': '',
            'notes': '   ',
        }, tenant=acme)
        assert not f.is_valid()
        assert 'notes' in f.errors

    def test_calibration_record_pass_without_notes_ok(self, acme, equipment):
        f = CalibrationRecordForm({
            'calibrated_at': '2026-04-30T10:00',
            'external_lab_name': '',
            'result': 'pass', 'next_due_at': '',
            'notes': '',
        }, tenant=acme)
        assert f.is_valid(), f.errors


@pytest.mark.django_db
class TestFileUploadAllowlist:
    def test_ncr_attachment_rejects_exe(self):
        bad = SimpleUploadedFile('virus.exe', b'MZx', content_type='application/octet-stream')
        f = NCRAttachmentForm({'description': 'bad'}, {'file': bad})
        assert not f.is_valid()
        assert 'file' in f.errors

    def test_ncr_attachment_accepts_pdf(self):
        ok = SimpleUploadedFile('report.pdf', b'%PDF', content_type='application/pdf')
        f = NCRAttachmentForm({'description': 'ok'}, {'file': ok})
        assert f.is_valid(), f.errors

    def test_ncr_attachment_rejects_oversize(self):
        # 26 MB > 25 MB cap
        big = SimpleUploadedFile('big.pdf', b'x' * (26 * 1024 * 1024))
        f = NCRAttachmentForm({'description': 'big'}, {'file': big})
        assert not f.is_valid()
