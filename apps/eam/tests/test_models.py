"""Model invariants, decimal validators, unique_together, auto-numbering, denorms."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from apps.eam import models as eam_m


@pytest.mark.django_db
class TestAsset:
    def test_auto_tag(self, acme, category):
        a = eam_m.Asset.objects.create(
            tenant=acme, name='Pump A', category=category,
            criticality='high', status='operational',
        )
        assert a.tag.startswith('ASSET-')
        assert a.tag.endswith(str(a.id).zfill(5))

    def test_unique_tag_per_tenant(self, acme):
        a = eam_m.Asset.objects.create(tenant=acme, name='X', criticality='low')
        with pytest.raises(IntegrityError):
            eam_m.Asset.objects.create(tenant=acme, name='Y', tag=a.tag, criticality='low')

    def test_negative_purchase_cost_rejected(self, acme):
        a = eam_m.Asset(tenant=acme, name='X', purchase_cost=Decimal('-1'))
        with pytest.raises(ValidationError):
            a.full_clean()

    def test_can_retire_helper(self, acme):
        a = eam_m.Asset.objects.create(tenant=acme, name='X', status='operational', criticality='low')
        assert a.can_retire() is True
        a.status = 'retired'
        assert a.can_retire() is False


@pytest.mark.django_db
class TestAssetCategory:
    def test_unique_per_parent_per_tenant(self, acme):
        # Note: SQL unique_together does not apply when a column is NULL, so
        # this test uses a non-NULL parent to actually trip the constraint.
        # The form-level check (AssetCategoryForm.clean) covers the NULL case.
        parent = eam_m.AssetCategory.objects.create(tenant=acme, name='Top')
        eam_m.AssetCategory.objects.create(tenant=acme, name='Sub', parent=parent)
        with pytest.raises(IntegrityError):
            eam_m.AssetCategory.objects.create(tenant=acme, name='Sub', parent=parent)

    def test_same_name_different_parents_allowed(self, acme):
        parent1 = eam_m.AssetCategory.objects.create(tenant=acme, name='A')
        parent2 = eam_m.AssetCategory.objects.create(tenant=acme, name='B')
        eam_m.AssetCategory.objects.create(tenant=acme, name='Sub', parent=parent1)
        eam_m.AssetCategory.objects.create(tenant=acme, name='Sub', parent=parent2)


@pytest.mark.django_db
class TestAssetSparePart:
    def test_unique_asset_product(self, acme, asset, cmp_product):
        eam_m.AssetSparePart.objects.create(
            tenant=acme, asset=asset, product=cmp_product,
            recommended_min_qty=Decimal('1'),
        )
        with pytest.raises(IntegrityError):
            eam_m.AssetSparePart.objects.create(
                tenant=acme, asset=asset, product=cmp_product,
                recommended_min_qty=Decimal('2'),
            )

    def test_negative_min_qty_rejected(self, acme, asset, cmp_product):
        sp = eam_m.AssetSparePart(
            tenant=acme, asset=asset, product=cmp_product,
            recommended_min_qty=Decimal('-1'),
        )
        with pytest.raises(ValidationError):
            sp.full_clean()


@pytest.mark.django_db
class TestAssetMeterReading:
    def test_negative_reading_rejected(self, acme, asset):
        r = eam_m.AssetMeterReading(
            tenant=acme, asset=asset, meter_type='hours',
            reading_value=Decimal('-0.01'),
        )
        with pytest.raises(ValidationError):
            r.full_clean()


@pytest.mark.django_db
class TestMaintenancePlan:
    def test_unique_name_per_asset(self, acme, asset):
        eam_m.MaintenancePlan.objects.create(
            tenant=acme, asset=asset, name='Lube',
            trigger_type='calendar', frequency_days=90,
        )
        with pytest.raises(IntegrityError):
            eam_m.MaintenancePlan.objects.create(
                tenant=acme, asset=asset, name='Lube',
                trigger_type='calendar', frequency_days=180,
            )

    def test_frequency_days_max(self, acme, asset):
        p = eam_m.MaintenancePlan(
            tenant=acme, asset=asset, name='X',
            trigger_type='calendar', frequency_days=99999,
        )
        with pytest.raises(ValidationError):
            p.full_clean()


@pytest.mark.django_db
class TestPMSchedule:
    def test_auto_schedule_number(self, acme, pm_plan):
        s = eam_m.PMSchedule.objects.create(
            tenant=acme, plan=pm_plan,
            scheduled_date=date.today() + timedelta(days=7),
        )
        assert s.schedule_number.startswith('PMS-')

    def test_is_actionable(self, acme, pm_plan):
        s = eam_m.PMSchedule.objects.create(
            tenant=acme, plan=pm_plan, scheduled_date=date.today(),
            status='scheduled',
        )
        assert s.is_actionable() is True
        s.status = 'completed'
        assert s.is_actionable() is False


@pytest.mark.django_db
class TestPMTaskCompletion:
    def test_unique_task_per_schedule(self, acme, pm_plan, pm_schedule):
        task = eam_m.MaintenanceTask.objects.create(
            tenant=acme, plan=pm_plan, sequence=10, description='Inspect',
        )
        eam_m.PMTaskCompletion.objects.create(
            tenant=acme, pm_schedule=pm_schedule, task=task, result='pass',
        )
        with pytest.raises(IntegrityError):
            eam_m.PMTaskCompletion.objects.create(
                tenant=acme, pm_schedule=pm_schedule, task=task, result='fail',
            )


@pytest.mark.django_db
class TestConditionMonitoringPoint:
    def test_unique_per_asset_per_name(self, acme, asset):
        eam_m.ConditionMonitoringPoint.objects.create(
            tenant=acme, asset=asset, name='Vibration',
            parameter='vibration', is_active=True,
        )
        with pytest.raises(IntegrityError):
            eam_m.ConditionMonitoringPoint.objects.create(
                tenant=acme, asset=asset, name='Vibration',
                parameter='temperature', is_active=True,
            )


@pytest.mark.django_db
class TestFailurePrediction:
    def test_confidence_pct_validators(self, acme, asset):
        p = eam_m.FailurePrediction(
            tenant=acme, asset=asset, summary='X',
            confidence_pct=Decimal('150'), status='open',
        )
        with pytest.raises(ValidationError):
            p.full_clean()

    def test_is_open(self, acme, asset):
        p = eam_m.FailurePrediction.objects.create(
            tenant=acme, asset=asset, summary='X', status='open',
        )
        assert p.is_open() is True
        p.status = 'resolved'
        assert p.is_open() is False


@pytest.mark.django_db
class TestMaintenanceWorkOrder:
    def test_auto_mwo_number(self, acme, asset, acme_admin):
        m = eam_m.MaintenanceWorkOrder.objects.create(
            tenant=acme, asset=asset, wo_type='corrective',
            title='X', reported_by=acme_admin, reported_at=timezone.now(),
        )
        assert m.mwo_number.startswith('MWO-')

    def test_state_helpers(self, mwo):
        assert mwo.is_editable() is True
        assert mwo.can_start() is True
        assert mwo.can_complete() is False
        mwo.status = 'in_progress'
        assert mwo.can_complete() is True
        assert mwo.can_hold() is True


@pytest.mark.django_db
class TestMWOLaborLog:
    def test_minutes_and_cost_computed(self, acme, mwo, acme_admin):
        start = timezone.now()
        end = start + timedelta(minutes=120)
        log = eam_m.MWOLaborLog.objects.create(
            tenant=acme, mwo=mwo, technician=acme_admin,
            started_at=start, ended_at=end, hourly_rate=Decimal('60'),
        )
        assert log.minutes == Decimal('120.00')
        assert log.total_cost == Decimal('120.00')


@pytest.mark.django_db
class TestMWOMaterialLog:
    def test_total_cost_computed(self, acme, mwo, cmp_product):
        ml = eam_m.MWOMaterialLog.objects.create(
            tenant=acme, mwo=mwo, product=cmp_product,
            quantity=Decimal('3'), unit_cost=Decimal('12.50'),
        )
        assert ml.total_cost == Decimal('37.50')


@pytest.mark.django_db
class TestDowntimeEvent:
    def test_minutes_computed(self, acme, asset):
        start = timezone.now()
        end = start + timedelta(minutes=45)
        d = eam_m.DowntimeEvent.objects.create(
            tenant=acme, asset=asset, started_at=start, ended_at=end,
            downtime_type='unplanned',
        )
        assert d.minutes == Decimal('45.00')


@pytest.mark.django_db
class TestTool:
    def test_auto_tool_id(self, acme):
        t = eam_m.Tool.objects.create(
            tenant=acme, name='Mill 1', tool_type='cutting_tool',
        )
        assert t.tool_id.startswith('TOOL-')

    def test_cycles_and_hours_remaining(self, acme):
        t = eam_m.Tool.objects.create(
            tenant=acme, name='X', tool_type='cutting_tool',
            expected_life_cycles=1000, current_cycles=600,
            expected_life_hours=Decimal('100'), current_hours=Decimal('25.5'),
        )
        assert t.cycles_remaining() == 400
        assert t.hours_remaining() == Decimal('74.5')

    def test_unset_life_returns_none(self, acme):
        t = eam_m.Tool.objects.create(tenant=acme, name='X', tool_type='gauge')
        assert t.cycles_remaining() is None
        assert t.hours_remaining() is None


@pytest.mark.django_db
class TestMoldCavityHistory:
    def test_unique_cavity_per_tool(self, acme, mold):
        eam_m.MoldCavityHistory.objects.create(
            tenant=acme, tool=mold, cavity_number=1, cycles=10, status='active',
        )
        with pytest.raises(IntegrityError):
            eam_m.MoldCavityHistory.objects.create(
                tenant=acme, tool=mold, cavity_number=1, cycles=20, status='active',
            )
