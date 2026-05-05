"""Form validation: L-01 unique_together, L-02 decimal bounds, L-14 per-workflow required."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.eam import forms, models as eam_m


@pytest.mark.django_db
class TestAssetCategoryForm_L01:
    def test_duplicate_name_same_parent_rejected(self, acme):
        eam_m.AssetCategory.objects.create(tenant=acme, name='Pumps')
        f = forms.AssetCategoryForm(
            data={'name': 'Pumps', 'parent': '', 'is_active': 'on'},
            tenant=acme,
        )
        assert not f.is_valid()
        assert 'name' in f.errors


@pytest.mark.django_db
class TestAssetForm:
    def test_commission_before_install_rejected(self, acme, category):
        today = date.today()
        f = forms.AssetForm(data={
            'name': 'X', 'category': category.pk,
            'criticality': 'medium', 'status': 'operational',
            'purchase_cost': '100', 'current_value': '50',
            'installation_date': today.isoformat(),
            'commissioning_date': (today - timedelta(days=1)).isoformat(),
            'is_active': 'on',
        }, tenant=acme)
        assert not f.is_valid()
        assert 'commissioning_date' in f.errors


@pytest.mark.django_db
class TestAssetSparePartForm_L01:
    def test_duplicate_product_for_asset_rejected(self, acme, asset, cmp_product):
        eam_m.AssetSparePart.objects.create(
            tenant=acme, asset=asset, product=cmp_product,
            recommended_min_qty=Decimal('1'),
        )
        f = forms.AssetSparePartForm(
            data={'product': cmp_product.pk, 'recommended_min_qty': '5',
                  'quantity_on_hand': '0'},
            tenant=acme, asset=asset,
        )
        assert not f.is_valid()
        assert 'product' in f.errors


@pytest.mark.django_db
class TestMaintenancePlanForm:
    def test_calendar_requires_frequency_days(self, acme, asset):
        f = forms.MaintenancePlanForm(data={
            'name': 'X', 'asset': asset.pk, 'trigger_type': 'calendar',
            'is_active': 'on',
        }, tenant=acme)
        assert not f.is_valid()
        assert 'frequency_days' in f.errors

    def test_meter_requires_frequency_meter(self, acme, asset):
        f = forms.MaintenancePlanForm(data={
            'name': 'X', 'asset': asset.pk, 'trigger_type': 'meter',
            'meter_type': 'hours', 'is_active': 'on',
        }, tenant=acme)
        assert not f.is_valid()
        assert 'frequency_meter' in f.errors

    def test_l01_unique_name_per_asset(self, acme, asset):
        eam_m.MaintenancePlan.objects.create(
            tenant=acme, asset=asset, name='Lube',
            trigger_type='calendar', frequency_days=30,
        )
        f = forms.MaintenancePlanForm(data={
            'name': 'Lube', 'asset': asset.pk, 'trigger_type': 'calendar',
            'frequency_days': '60', 'is_active': 'on',
        }, tenant=acme)
        assert not f.is_valid()
        assert 'name' in f.errors


@pytest.mark.django_db
class TestPMScheduleCompleteForm_L14:
    def test_completion_requires_at_least_one_task_result(self, acme, pm_plan, pm_schedule):
        eam_m.MaintenanceTask.objects.create(
            tenant=acme, plan=pm_plan, sequence=10, description='Inspect',
        )
        f = forms.PMScheduleCompleteForm(data={'notes': ''}, schedule=pm_schedule)
        assert not f.is_valid()

    def test_no_tasks_means_no_completion_requirement(self, acme, pm_plan, pm_schedule):
        f = forms.PMScheduleCompleteForm(data={'notes': ''}, schedule=pm_schedule)
        assert f.is_valid()


@pytest.mark.django_db
class TestConditionPointForm_L01:
    def test_duplicate_name_per_asset_rejected(self, acme, asset):
        eam_m.ConditionMonitoringPoint.objects.create(
            tenant=acme, asset=asset, name='Vib', parameter='vibration',
        )
        f = forms.ConditionMonitoringPointForm(data={
            'asset': asset.pk, 'name': 'Vib', 'parameter': 'temperature',
            'is_active': 'on',
        }, tenant=acme)
        assert not f.is_valid()

    def test_low_alarm_must_be_below_high(self, acme, asset):
        f = forms.ConditionMonitoringPointForm(data={
            'asset': asset.pk, 'name': 'X', 'parameter': 'pressure',
            'low_alarm': '10', 'high_alarm': '5', 'is_active': 'on',
        }, tenant=acme)
        assert not f.is_valid()
        assert 'high_alarm' in f.errors


@pytest.mark.django_db
class TestFailurePredictionResolveForm_L14:
    def test_resolution_notes_required(self):
        f = forms.FailurePredictionResolveForm(
            data={'outcome': 'resolved', 'resolution_notes': '   '},
        )
        assert not f.is_valid()
        assert 'resolution_notes' in f.errors

    def test_valid_when_notes_present(self):
        f = forms.FailurePredictionResolveForm(
            data={'outcome': 'resolved', 'resolution_notes': 'Replaced bearing.'},
        )
        assert f.is_valid()


@pytest.mark.django_db
class TestMWOCompleteForm_L14:
    def test_resolution_notes_required(self):
        f = forms.MWOCompleteForm(data={'resolution_notes': '  ', 'root_cause': 'X'})
        assert not f.is_valid()


@pytest.mark.django_db
class TestMWOLaborLogForm:
    def test_end_before_start_rejected(self, acme, acme_admin):
        f = forms.MWOLaborLogForm(data={
            'technician': acme_admin.pk,
            'started_at': '2026-05-05T12:00',
            'ended_at': '2026-05-05T11:00',
            'hourly_rate': '60', 'notes': '',
        }, tenant=acme)
        assert not f.is_valid()
        assert 'ended_at' in f.errors


@pytest.mark.django_db
class TestToolForm:
    def test_mold_requires_cavity_count(self, acme):
        f = forms.ToolForm(data={
            'name': 'X', 'tool_type': 'mold', 'status': 'available',
            'expected_life_cycles': 0, 'expected_life_hours': '0',
            'cavity_count': 0, 'is_active': 'on',
            'purchase_cost': '0',
        }, tenant=acme)
        assert not f.is_valid()
        assert 'cavity_count' in f.errors

    def test_non_mold_with_cavity_rejected(self, acme):
        f = forms.ToolForm(data={
            'name': 'X', 'tool_type': 'cutting_tool', 'status': 'available',
            'expected_life_cycles': 0, 'expected_life_hours': '0',
            'cavity_count': 4, 'is_active': 'on',
            'purchase_cost': '0',
        }, tenant=acme)
        assert not f.is_valid()
        assert 'cavity_count' in f.errors


@pytest.mark.django_db
class TestToolMaintenanceRecordForm:
    def test_disallowed_extension_rejected(self, acme, tool):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = forms.ToolMaintenanceRecordForm(
            data={
                'record_type': 'sharpening',
                'performed_at': '2026-05-05',
                'cost': '40', 'notes': 'x',
            },
            files={'attachment': SimpleUploadedFile('evil.exe', b'data')},
            tenant=acme,
        )
        assert not f.is_valid()
        assert 'attachment' in f.errors


@pytest.mark.django_db
class TestMoldCavityHistoryForm:
    def test_only_for_mold_type(self, acme, tool):
        # tool is cutting_tool fixture
        f = forms.MoldCavityHistoryForm(
            data={'cavity_number': 1, 'cycles': 0, 'defect_count': 0, 'status': 'active'},
            tenant=acme, tool=tool,
        )
        assert not f.is_valid()

    def test_cavity_number_caps_at_tool_count(self, acme, mold):
        f = forms.MoldCavityHistoryForm(
            data={'cavity_number': 99, 'cycles': 0, 'defect_count': 0, 'status': 'active'},
            tenant=acme, tool=mold,
        )
        assert not f.is_valid()
        assert 'cavity_number' in f.errors
