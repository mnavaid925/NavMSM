"""RBAC matrix + multi-tenant IDOR + CSRF (Lesson L-10).

Every admin-gated POST: verify staff_client gets a redirect AND the underlying
record's status / data did not change.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.qms.models import (
    CalibrationStandard, IncomingInspection, IncomingInspectionPlan,
    MeasurementEquipment, NonConformanceReport,
)


@pytest.mark.django_db
class TestRBACMatrix:
    """Each staff POST should redirect AND not mutate."""

    def test_staff_cannot_create_iqc_plan(self, staff_client, acme, raw_product):
        r = staff_client.post(reverse('qms:iqc_plan_create'), {
            'product': raw_product.pk, 'aql_level': 'II', 'sample_method': 'single',
            'aql_value': '2.5', 'version': '1.0', 'is_active': True,
        })
        assert r.status_code == 302
        assert not IncomingInspectionPlan.objects.filter(product=raw_product).exists()

    def test_staff_cannot_create_equipment(self, staff_client, acme):
        r = staff_client.post(reverse('qms:equipment_create'), {
            'name': 'X', 'equipment_type': 'caliper', 'serial_number': 'SN-XX',
            'manufacturer': '', 'model_number': '',
            'range_min': '', 'range_max': '', 'unit_of_measure': '',
            'tolerance': '', 'calibration_interval_days': 365,
            'status': 'active', 'is_active': True, 'notes': '',
        })
        assert r.status_code == 302
        assert not MeasurementEquipment.objects.filter(serial_number='SN-XX').exists()

    def test_staff_cannot_close_ncr(self, staff_client, open_ncr):
        open_ncr.status = 'resolved'; open_ncr.save()
        r = staff_client.post(reverse('qms:ncr_close', args=[open_ncr.pk]),
                              {'resolution_summary': 'Done'})
        assert r.status_code == 302
        open_ncr.refresh_from_db()
        # Status should NOT have transitioned to closed
        assert open_ncr.status == 'resolved'

    def test_staff_cannot_retire_equipment(self, staff_client, equipment):
        r = staff_client.post(reverse('qms:equipment_retire', args=[equipment.pk]))
        assert r.status_code == 302
        equipment.refresh_from_db()
        assert equipment.status == 'active'

    def test_staff_cannot_create_calibration_standard(self, staff_client):
        r = staff_client.post(reverse('qms:standard_create'), {
            'name': 'Bad std', 'standard_number': 'STD-BAD',
            'traceable_to': '', 'description': '', 'is_active': True,
        })
        assert r.status_code == 302
        assert not CalibrationStandard.objects.filter(standard_number='STD-BAD').exists()

    def test_staff_cannot_release_coa(self, staff_client, acme, fqc_plan):
        from apps.qms.models import FinalInspection
        i = FinalInspection.objects.create(
            tenant=acme, inspection_number='FQC-RBAC', plan=fqc_plan,
            quantity_tested=Decimal('100'), status='passed',
        )
        # Generate first as admin
        from django.test import Client
        from apps.accounts.models import User
        admin = User.objects.create_user(
            username='gen_admin', password='pw', tenant=acme, is_tenant_admin=True,
        )
        ac = Client(); ac.force_login(admin)
        ac.get(reverse('qms:coa_render', args=[i.pk]))
        # Now staff tries to release
        r = staff_client.post(reverse('qms:coa_release', args=[i.pk]))
        assert r.status_code == 302
        i.refresh_from_db()
        coa = getattr(i, 'coa', None)
        assert coa is not None
        assert coa.released_to_customer is False


@pytest.mark.django_db
class TestMultiTenantIsolation:
    """Cross-tenant access must 404 (IDOR guard)."""

    def test_iqc_plan_detail_cross_tenant_404(self, globex_client, iqc_plan):
        r = globex_client.get(reverse('qms:iqc_plan_detail', args=[iqc_plan.pk]))
        assert r.status_code == 404

    def test_ncr_detail_cross_tenant_404(self, globex_client, open_ncr):
        r = globex_client.get(reverse('qms:ncr_detail', args=[open_ncr.pk]))
        assert r.status_code == 404

    def test_equipment_detail_cross_tenant_404(self, globex_client, equipment):
        r = globex_client.get(reverse('qms:equipment_detail', args=[equipment.pk]))
        assert r.status_code == 404

    def test_iqc_inspection_workflow_blocked_cross_tenant(self, globex_client, acme, raw_product, iqc_plan):
        i = IncomingInspection.objects.create(
            tenant=acme, inspection_number='IQC-X', product=raw_product,
            plan=iqc_plan, received_qty=Decimal('100'), status='in_inspection',
        )
        r = globex_client.post(reverse('qms:iqc_inspection_accept', args=[i.pk]))
        # 302 because status update with tenant filter just doesn't match;
        # the row is not transitioned.
        i.refresh_from_db()
        assert i.status == 'in_inspection'


@pytest.mark.django_db
class TestAnonymousRedirect:
    def test_anon_cannot_view_dashboard(self, client):
        r = client.get(reverse('qms:index'))
        assert r.status_code == 302  # to login

    def test_anon_cannot_post_create(self, client, raw_product, acme):
        r = client.post(reverse('qms:iqc_plan_create'), {
            'product': raw_product.pk, 'aql_level': 'II',
            'sample_method': 'single', 'aql_value': '2.5',
            'version': '1.0', 'is_active': True,
        })
        assert r.status_code == 302
        assert not IncomingInspectionPlan.objects.filter(version='1.0', product=raw_product).exists()
