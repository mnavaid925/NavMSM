"""Module 15 - workflow / state-transition view tests.

Covers the POST handlers for status transitions:
    * Device retire / reactivate
    * DigitalTwin activate / archive / snapshot / recompute
    * TwinSimulationScenario run
    * AlertRule activate / deactivate
    * AnomalyDetection acknowledge / resolve / false_positive
    * OEEPeriod recompute
    * DeviceBroker heartbeat
"""
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone


pytestmark = pytest.mark.django_db


def test_device_retire(admin_client, device):
    r = admin_client.post(reverse('iot:device_retire', args=[device.pk]))
    assert r.status_code in (302,)
    device.refresh_from_db()
    assert device.status == 'decommissioned'


def test_device_retire_blocked_when_decommissioned(admin_client, device):
    device.status = 'decommissioned'
    device.save()
    r = admin_client.post(reverse('iot:device_retire', args=[device.pk]))
    assert r.status_code in (302,)
    device.refresh_from_db()
    assert device.status == 'decommissioned'  # unchanged


def test_device_reactivate(admin_client, device):
    device.status = 'inactive'
    device.save()
    r = admin_client.post(reverse('iot:device_reactivate', args=[device.pk]))
    assert r.status_code == 302
    device.refresh_from_db()
    assert device.status == 'active'


def test_twin_activate(admin_client, acme):
    from apps.iot.models import DigitalTwin
    t = DigitalTwin.objects.create(tenant=acme, name='T1', twin_type='machine')
    r = admin_client.post(reverse('iot:twin_activate', args=[t.pk]))
    assert r.status_code == 302
    t.refresh_from_db()
    assert t.status == 'active'


def test_twin_archive(admin_client, acme):
    from apps.iot.models import DigitalTwin
    t = DigitalTwin.objects.create(tenant=acme, name='T1', twin_type='machine', status='active')
    r = admin_client.post(reverse('iot:twin_archive', args=[t.pk]))
    assert r.status_code == 302
    t.refresh_from_db()
    assert t.status == 'archived'


def test_twin_archive_already_archived_blocked(admin_client, acme):
    from apps.iot.models import DigitalTwin
    t = DigitalTwin.objects.create(tenant=acme, name='T1', twin_type='machine', status='archived')
    r = admin_client.post(reverse('iot:twin_archive', args=[t.pk]))
    assert r.status_code == 302
    t.refresh_from_db()
    assert t.status == 'archived'


def test_twin_snapshot_creates_row(admin_client, acme):
    from apps.iot.models import DigitalTwin, TwinStateSnapshot
    t = DigitalTwin.objects.create(tenant=acme, name='T1', twin_type='machine', status='active')
    before = TwinStateSnapshot.objects.filter(twin=t).count()
    admin_client.post(reverse('iot:twin_snapshot', args=[t.pk]),
                      data={'notes': 'qa snapshot'})
    after = TwinStateSnapshot.objects.filter(twin=t).count()
    assert after == before + 1


def test_twin_recompute(admin_client, acme):
    from apps.iot.models import DigitalTwin
    t = DigitalTwin.objects.create(tenant=acme, name='T1', twin_type='machine', status='active')
    r = admin_client.post(reverse('iot:twin_recompute', args=[t.pk]))
    assert r.status_code == 302


def test_twin_scenario_run_completes(admin_client, acme):
    from apps.iot.models import DigitalTwin, TwinStateAttribute, TwinSimulationScenario
    t = DigitalTwin.objects.create(tenant=acme, name='T1', twin_type='machine', status='active')
    TwinStateAttribute.objects.create(
        tenant=acme, twin=t, name='speed', attribute_type='measurement',
    )
    s = TwinSimulationScenario.objects.create(
        tenant=acme, twin=t, name='S1',
        input_payload={'speed': 100}, expected_output={},
    )
    r = admin_client.post(reverse('iot:twin_scenario_run', args=[s.pk]))
    assert r.status_code == 302
    s.refresh_from_db()
    assert s.status in ('completed', 'failed')
    assert s.run_at is not None


def test_alert_rule_activate(admin_client, alert_rule):
    alert_rule.is_active = False
    alert_rule.save()
    r = admin_client.post(reverse('iot:rule_activate', args=[alert_rule.pk]))
    assert r.status_code == 302
    alert_rule.refresh_from_db()
    assert alert_rule.is_active is True


def test_alert_rule_deactivate(admin_client, alert_rule):
    r = admin_client.post(reverse('iot:rule_deactivate', args=[alert_rule.pk]))
    assert r.status_code == 302
    alert_rule.refresh_from_db()
    assert alert_rule.is_active is False


def test_anomaly_acknowledge(admin_client, acme, alert_rule, reading):
    from apps.iot.models import AnomalyDetection
    d = AnomalyDetection.objects.create(
        tenant=acme, rule=alert_rule, source_reading=reading,
        severity='high', status='new',
    )
    r = admin_client.post(reverse('iot:detection_acknowledge', args=[d.pk]))
    assert r.status_code == 302
    d.refresh_from_db()
    assert d.status == 'acknowledged'
    assert d.acknowledged_by_id is not None
    assert d.acknowledged_at is not None


def test_anomaly_resolve_requires_notes(admin_client, acme, alert_rule, reading):
    from apps.iot.models import AnomalyDetection
    d = AnomalyDetection.objects.create(
        tenant=acme, rule=alert_rule, source_reading=reading,
        severity='high', status='new',
    )
    r = admin_client.post(reverse('iot:detection_resolve', args=[d.pk]),
                          data={'resolution_notes': '   '})
    assert r.status_code == 200  # form re-rendered
    d.refresh_from_db()
    assert d.status == 'new'  # not changed


def test_anomaly_resolve_with_notes(admin_client, acme, alert_rule, reading):
    from apps.iot.models import AnomalyDetection
    d = AnomalyDetection.objects.create(
        tenant=acme, rule=alert_rule, source_reading=reading,
        severity='high', status='new',
    )
    r = admin_client.post(reverse('iot:detection_resolve', args=[d.pk]),
                          data={'resolution_notes': 'Replaced sensor.'})
    assert r.status_code == 302
    d.refresh_from_db()
    assert d.status == 'resolved'
    assert d.resolution_notes == 'Replaced sensor.'


def test_anomaly_false_positive_requires_notes(admin_client, acme, alert_rule, reading):
    from apps.iot.models import AnomalyDetection
    d = AnomalyDetection.objects.create(
        tenant=acme, rule=alert_rule, source_reading=reading,
        severity='high', status='new',
    )
    r = admin_client.post(reverse('iot:detection_false_positive', args=[d.pk]),
                          data={'resolution_notes': ''})
    assert r.status_code == 200
    d.refresh_from_db()
    assert d.status == 'new'


def test_anomaly_false_positive_with_notes(admin_client, acme, alert_rule, reading):
    from apps.iot.models import AnomalyDetection
    d = AnomalyDetection.objects.create(
        tenant=acme, rule=alert_rule, source_reading=reading,
        severity='high', status='new',
    )
    r = admin_client.post(reverse('iot:detection_false_positive', args=[d.pk]),
                          data={'resolution_notes': 'Sensor calibration drift, not a real fault.'})
    assert r.status_code == 302
    d.refresh_from_db()
    assert d.status == 'false_positive'


def test_oee_period_recompute(admin_client, acme):
    from datetime import date
    from apps.eam.models import Asset, AssetCategory
    from apps.iot.models import OEEPeriod
    cat = AssetCategory.objects.create(tenant=acme, code='C1', name='C1')
    a = Asset.objects.create(tenant=acme, category=cat, tag='A1', name='A')
    p = OEEPeriod.objects.create(
        tenant=acme, asset=a, period_date=date.today(),
        planned_run_minutes=Decimal('480'),
    )
    r = admin_client.post(reverse('iot:oee_period_recompute', args=[p.pk]))
    assert r.status_code == 302


def test_broker_heartbeat_success(admin_client, broker):
    r = admin_client.post(reverse('iot:broker_heartbeat', args=[broker.pk]),
                          data={'success': '1'})
    assert r.status_code == 302
    broker.refresh_from_db()
    assert broker.last_heartbeat_at is not None
    assert broker.status == 'active'


def test_broker_heartbeat_failure(admin_client, broker):
    r = admin_client.post(reverse('iot:broker_heartbeat', args=[broker.pk]),
                          data={'error_message': 'Connection refused'})
    assert r.status_code == 302
    broker.refresh_from_db()
    assert broker.status == 'error'
    assert broker.error_message == 'Connection refused'
