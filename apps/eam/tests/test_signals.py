"""Audit signal emission, cross-module hooks, L-18 dispatch_uid presence guard."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db.models.signals import post_save, pre_save
from django.utils import timezone

from apps.eam import models as eam_m
from apps.tenants.models import TenantAuditLog


@pytest.mark.django_db
class TestL18DispatchUIDPresence:
    """Per Lesson L-18, every factory-registered handler must remain attached.

    If they got garbage-collected (default weak=True), the receivers list
    would no longer contain them and audit signals would silently never fire.
    """

    REQUIRED_PRE = [
        'eam.asset_pre', 'eam.pm_schedule_pre', 'eam.prediction_pre',
        'eam.mwo_pre', 'eam.tool_pre',
    ]
    REQUIRED_POST = [
        'eam.asset_post', 'eam.pm_schedule_post', 'eam.prediction_post',
        'eam.mwo_post', 'eam.tool_post',
    ]
    REQUIRED_CROSS = [
        'eam_andon_to_mwo', 'eam_production_report_to_tool_usage',
    ]

    def _uids(self, signal):
        return {entry[0][0] for entry in signal.receivers}

    def test_pre_save_handlers_attached(self):
        uids = self._uids(pre_save)
        for uid in self.REQUIRED_PRE:
            assert uid in uids, f'Missing pre_save uid: {uid}'

    def test_post_save_handlers_attached(self):
        uids = self._uids(post_save)
        for uid in self.REQUIRED_POST + self.REQUIRED_CROSS:
            assert uid in uids, f'Missing post_save uid: {uid}'


@pytest.mark.django_db
class TestAssetAudit:
    def test_create_emits_audit(self, acme):
        before = TenantAuditLog.objects.filter(action='eam.asset.created').count()
        eam_m.Asset.objects.create(tenant=acme, name='X', criticality='low')
        after = TenantAuditLog.objects.filter(action='eam.asset.created').count()
        assert after == before + 1

    def test_status_change_emits_audit(self, acme, asset):
        eam_m.Asset.all_objects.filter(pk=asset.pk).update()  # no-op; trigger via instance
        asset.status = 'down'
        asset.save()
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='eam.asset.down',
        ).exists()


@pytest.mark.django_db
class TestMWOAudit:
    def test_status_change_emits_audit(self, acme, mwo):
        mwo.status = 'scheduled'
        mwo.save()
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='eam.mwo.scheduled',
        ).exists()


@pytest.mark.django_db
class TestConditionReadingSpawnsPrediction:
    def test_critical_reading_creates_prediction(self, acme, monitoring_point):
        # high_alarm=5.0; reading=10 -> critical -> auto-spawn FailurePrediction.
        eam_m.ConditionReading.objects.create(
            tenant=acme, point=monitoring_point,
            reading_value=Decimal('10'),
        )
        assert eam_m.FailurePrediction.objects.filter(
            tenant=acme, asset=monitoring_point.asset, status='open',
        ).exists()

    def test_normal_reading_does_not_spawn_prediction(self, acme, monitoring_point):
        eam_m.ConditionReading.objects.create(
            tenant=acme, point=monitoring_point, reading_value=Decimal('1'),
        )
        assert not eam_m.FailurePrediction.objects.filter(
            tenant=acme, asset=monitoring_point.asset,
        ).exists()

    def test_existing_open_prediction_not_duplicated(self, acme, asset, monitoring_point):
        eam_m.FailurePrediction.objects.create(
            tenant=acme, asset=asset, summary='Existing', status='open',
        )
        eam_m.ConditionReading.objects.create(
            tenant=acme, point=monitoring_point, reading_value=Decimal('10'),
        )
        # Still only 1 prediction exists for this asset.
        assert eam_m.FailurePrediction.objects.filter(
            tenant=acme, asset=asset,
        ).count() == 1


@pytest.mark.django_db
class TestDowntimeRefreshesMwo:
    def test_event_save_updates_parent_mwo_minutes(self, acme, asset, mwo):
        now = timezone.now()
        eam_m.DowntimeEvent.objects.create(
            tenant=acme, asset=asset, mwo=mwo,
            started_at=now, ended_at=now + timedelta(minutes=15),
            downtime_type='unplanned',
        )
        mwo.refresh_from_db()
        assert mwo.downtime_minutes == Decimal('15.00')


@pytest.mark.django_db
class TestAndonAutoSpawnsBreakdownMWO:
    def test_equipment_andon_with_asset_creates_mwo(self, acme, asset, acme_admin):
        from apps.mes import models as mes_m
        from apps.pps.models import WorkCenter
        wc = WorkCenter.objects.create(tenant=acme, code='WC1', name='WC 1')
        before = eam_m.MaintenanceWorkOrder.all_objects.count()
        andon = mes_m.AndonAlert.objects.create(
            tenant=acme, alert_number='AND-1',
            alert_type='equipment', severity='high', title='Pump down',
            work_center=wc, raised_by=acme_admin, raised_at=timezone.now(),
            asset=asset,
        )
        after = eam_m.MaintenanceWorkOrder.all_objects.count()
        assert after == before + 1
        spawned = eam_m.MaintenanceWorkOrder.all_objects.get(source_andon=andon)
        assert spawned.wo_type == 'breakdown'
        assert spawned.asset_id == asset.pk

    def test_no_asset_link_no_mwo_spawned(self, acme, acme_admin):
        from apps.mes import models as mes_m
        from apps.pps.models import WorkCenter
        wc = WorkCenter.objects.create(tenant=acme, code='WC2', name='WC 2')
        before = eam_m.MaintenanceWorkOrder.all_objects.count()
        mes_m.AndonAlert.objects.create(
            tenant=acme, alert_number='AND-2',
            alert_type='equipment', severity='high', title='X',
            work_center=wc, raised_by=acme_admin, raised_at=timezone.now(),
        )
        assert eam_m.MaintenanceWorkOrder.all_objects.count() == before

    def test_non_equipment_alert_does_not_spawn(self, acme, asset, acme_admin):
        from apps.mes import models as mes_m
        from apps.pps.models import WorkCenter
        wc = WorkCenter.objects.create(tenant=acme, code='WC3', name='WC 3')
        before = eam_m.MaintenanceWorkOrder.all_objects.count()
        mes_m.AndonAlert.objects.create(
            tenant=acme, alert_number='AND-3',
            alert_type='quality', severity='high', title='Defect',
            work_center=wc, raised_by=acme_admin, raised_at=timezone.now(),
            asset=asset,
        )
        assert eam_m.MaintenanceWorkOrder.all_objects.count() == before
