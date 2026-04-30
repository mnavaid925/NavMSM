"""Model invariants for QMS - validators, unique_together, helpers."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.qms.models import (
    CalibrationRecord, CertificateOfAnalysis, CorrectiveAction,
    FinalInspection, IncomingInspection, IncomingInspectionPlan,
    MeasurementEquipment, NonConformanceReport, ProcessInspectionPlan,
    SPCChart, ToleranceVerification,
)


@pytest.mark.django_db
class TestModelStrings:
    def test_iqc_plan_str(self, iqc_plan):
        s = str(iqc_plan)
        assert 'IQC' in s and iqc_plan.product.sku in s

    def test_ipqc_plan_str(self, ipqc_plan):
        assert 'IPQC' in str(ipqc_plan)

    def test_fqc_plan_str(self, fqc_plan):
        assert 'FQC' in str(fqc_plan)

    def test_ncr_str_includes_severity_and_title(self, open_ncr):
        s = str(open_ncr)
        assert 'NCR-T0001' in s and 'Major' in s

    def test_equipment_str(self, equipment):
        assert 'EQP-T0001' in str(equipment)


@pytest.mark.django_db
class TestUniqueConstraints:
    def test_iqc_plan_unique_per_tenant_product_version(self, acme, raw_product):
        IncomingInspectionPlan.objects.create(
            tenant=acme, product=raw_product, version='2.0',
            aql_level='II', aql_value=Decimal('2.5'), sample_method='single',
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                IncomingInspectionPlan.objects.create(
                    tenant=acme, product=raw_product, version='2.0',
                    aql_level='II', aql_value=Decimal('1.0'),
                    sample_method='single',
                )

    def test_equipment_serial_unique_per_tenant(self, acme, equipment):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                MeasurementEquipment.objects.create(
                    tenant=acme, equipment_number='EQP-T0002',
                    name='Dup', equipment_type='caliper',
                    serial_number='SN-T-001',
                    calibration_interval_days=365,
                )

    def test_equipment_serial_can_repeat_across_tenants(self, acme, globex, equipment):
        # Lesson L-01 boundary check - unique only within tenant
        MeasurementEquipment.objects.create(
            tenant=globex, equipment_number='EQP-G-1', name='Same SN',
            equipment_type='caliper', serial_number='SN-T-001',
            calibration_interval_days=365,
        )

    def test_ipqc_plan_unique_per_product_routing_op(self, acme, fg_product, routing_operation):
        ProcessInspectionPlan.objects.create(
            tenant=acme, product=fg_product, routing_operation=routing_operation,
            name='dup1', frequency='every_part', frequency_value=1,
            chart_type='none',
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ProcessInspectionPlan.objects.create(
                    tenant=acme, product=fg_product,
                    routing_operation=routing_operation,
                    name='dup2', frequency='every_part', frequency_value=1,
                    chart_type='none',
                )


@pytest.mark.django_db
class TestValidatorBounds:
    """Lesson L-02 - explicit MinValueValidator on Decimal fields."""

    def test_iqc_plan_aql_value_min(self, acme, raw_product):
        plan = IncomingInspectionPlan(
            tenant=acme, product=raw_product, aql_level='II',
            aql_value=Decimal('-1'), sample_method='single', version='1.0',
        )
        with pytest.raises(ValidationError):
            plan.full_clean()

    def test_iqc_plan_aql_value_max(self, acme, raw_product):
        plan = IncomingInspectionPlan(
            tenant=acme, product=raw_product, aql_level='II',
            aql_value=Decimal('150'), sample_method='single', version='1.0',
        )
        with pytest.raises(ValidationError):
            plan.full_clean()

    def test_equipment_calibration_interval_min(self, acme):
        eq = MeasurementEquipment(
            tenant=acme, equipment_number='EQP-X', name='X',
            equipment_type='caliper', serial_number='SN-X',
            calibration_interval_days=0,  # below min
        )
        with pytest.raises(ValidationError):
            eq.full_clean()

    def test_equipment_calibration_interval_max(self, acme):
        eq = MeasurementEquipment(
            tenant=acme, equipment_number='EQP-Y', name='Y',
            equipment_type='caliper', serial_number='SN-Y',
            calibration_interval_days=10000,  # above max 3650
        )
        with pytest.raises(ValidationError):
            eq.full_clean()

    def test_iqc_inspection_received_qty_must_be_positive(self, acme, raw_product, iqc_plan):
        i = IncomingInspection(
            tenant=acme, inspection_number='IQC-VAL-1', product=raw_product,
            plan=iqc_plan, received_qty=Decimal('0'),
        )
        with pytest.raises(ValidationError):
            i.full_clean()

    def test_ipqc_subgroup_size_min(self, acme, fg_product, routing_operation):
        plan = ProcessInspectionPlan(
            tenant=acme, product=fg_product, routing_operation=routing_operation,
            name='bad', frequency='every_part', frequency_value=1,
            chart_type='x_bar_r', subgroup_size=1,  # below min 2
        )
        with pytest.raises(ValidationError):
            plan.full_clean()


@pytest.mark.django_db
class TestStateMachineHelpers:
    def test_iqc_inspection_can_start_only_pending(self, acme, raw_product, iqc_plan):
        i = IncomingInspection.objects.create(
            tenant=acme, inspection_number='IQC-S-1', product=raw_product,
            plan=iqc_plan, received_qty=Decimal('100'), status='pending',
        )
        assert i.can_start()
        i.status = 'accepted'
        assert not i.can_start()

    def test_iqc_can_accept_only_in_inspection(self, acme, raw_product, iqc_plan):
        i = IncomingInspection.objects.create(
            tenant=acme, inspection_number='IQC-S-2', product=raw_product,
            plan=iqc_plan, received_qty=Decimal('100'), status='in_inspection',
        )
        assert i.can_accept() and i.can_reject()
        i.status = 'pending'
        assert not i.can_accept()

    def test_fqc_can_generate_coa_only_passed(self, acme, fg_product, fqc_plan):
        i = FinalInspection.objects.create(
            tenant=acme, inspection_number='FQC-S-1', plan=fqc_plan,
            quantity_tested=Decimal('100'), status='passed',
        )
        assert i.can_generate_coa()
        i.status = 'failed'
        assert not i.can_generate_coa()

    def test_ncr_workflow_helpers(self, open_ncr):
        assert open_ncr.is_editable()
        assert open_ncr.can_investigate()
        assert open_ncr.can_cancel()
        open_ncr.status = 'closed'
        assert not open_ncr.is_editable()
        assert not open_ncr.can_cancel()


@pytest.mark.django_db
class TestCalibrationRecordCleanRule:
    """Lesson L-14 - notes required when result is fail."""

    def test_fail_without_notes_rejected(self, equipment):
        rec = CalibrationRecord(
            tenant=equipment.tenant, record_number='CAL-X-1',
            equipment=equipment, calibrated_at=timezone.now(),
            result='fail', notes='',
        )
        with pytest.raises(ValidationError):
            rec.full_clean()

    def test_fail_with_notes_passes(self, equipment):
        rec = CalibrationRecord(
            tenant=equipment.tenant, record_number='CAL-X-2',
            equipment=equipment, calibrated_at=timezone.now(),
            result='fail', notes='Tool damaged - sent for repair.',
        )
        rec.full_clean()  # should not raise

    def test_pass_without_notes_passes(self, equipment):
        rec = CalibrationRecord(
            tenant=equipment.tenant, record_number='CAL-X-3',
            equipment=equipment, calibrated_at=timezone.now(),
            result='pass', notes='',
        )
        rec.full_clean()  # should not raise
