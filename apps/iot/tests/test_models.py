"""Module 15 - model unit tests.

Covers:
    * Auto-numbering on save() (BRK-, DEV-, IR-, IRB-, DT-, TSC-, OEEP-, AR-, AD-)
    * __str__ contracts
    * Status helper booleans (is_*())
    * OEEPeriod recompute_pcts() math
    * DeviceProtocol shared catalog (no tenant)
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.iot import models as I


pytestmark = pytest.mark.django_db


def test_protocol_str(mqtt_protocol):
    assert str(mqtt_protocol) == 'mqtt - MQTT'


def test_protocol_no_tenant(mqtt_protocol):
    assert not hasattr(mqtt_protocol, 'tenant')


def test_broker_auto_number(broker):
    assert broker.broker_number.startswith('BRK-')
    assert broker.broker_number == 'BRK-00001'


def test_broker_str(broker):
    assert broker.broker_number in str(broker)
    assert broker.name in str(broker)


def test_broker_second_increments(acme, mqtt_protocol):
    I.DeviceBroker.objects.create(tenant=acme, name='B1', protocol=mqtt_protocol, host='h', port=1)
    b2 = I.DeviceBroker.objects.create(tenant=acme, name='B2', protocol=mqtt_protocol, host='h', port=1)
    assert b2.broker_number == 'BRK-00002'


def test_device_auto_number(device):
    assert device.device_number == 'DEV-00001'


def test_device_is_retirable(device):
    assert device.is_retirable() is True
    device.status = 'decommissioned'
    assert device.is_retirable() is False


def test_device_is_reactivatable(device):
    device.status = 'inactive'
    assert device.is_reactivatable() is True


def test_tag_str(temp_tag):
    assert temp_tag.device.device_number in str(temp_tag)
    assert temp_tag.name in str(temp_tag)


def test_reading_auto_number(reading):
    assert reading.entry_number == 'IR-00001'


def test_reading_value_display_numeric(reading):
    assert reading.value_display() == '72.5000'


def test_reading_value_display_text(acme, temp_tag):
    r = I.IoTReading.objects.create(
        tenant=acme, device_tag=temp_tag, timestamp=timezone.now(),
        value_text='OK', quality='good', source='manual',
    )
    assert r.value_display() == 'OK'


def test_reading_value_display_bool(acme, temp_tag):
    r = I.IoTReading.objects.create(
        tenant=acme, device_tag=temp_tag, timestamp=timezone.now(),
        value_bool=True, quality='good', source='manual',
    )
    assert r.value_display() == 'true'


def test_reading_value_display_blank(acme, temp_tag):
    r = I.IoTReading.objects.create(
        tenant=acme, device_tag=temp_tag, timestamp=timezone.now(),
        quality='good', source='manual',
    )
    assert r.value_display() == '-'


def test_batch_auto_number(acme):
    b = I.IoTReadingBatch.objects.create(tenant=acme, source_format='seed')
    assert b.batch_number == 'IRB-00001'


def test_alert_rule_auto_number(alert_rule):
    assert alert_rule.rule_number == 'AR-00001'


def test_alert_rule_channel_list(alert_rule):
    alert_rule.notification_channels = 'in_app, email, mes_andon'
    assert alert_rule.channel_list() == ['in_app', 'email', 'mes_andon']


def test_twin_auto_number(acme):
    t = I.DigitalTwin.objects.create(tenant=acme, name='T1', twin_type='machine')
    assert t.twin_number == 'DT-00001'
    assert t.is_activatable() is True
    assert t.is_deletable() is True


def test_twin_activate_blocks_when_active(acme):
    t = I.DigitalTwin.objects.create(tenant=acme, name='T1', twin_type='machine', status='active')
    assert t.is_activatable() is False


def test_scenario_auto_number(acme):
    twin = I.DigitalTwin.objects.create(tenant=acme, name='T1', twin_type='machine')
    s = I.TwinSimulationScenario.objects.create(tenant=acme, twin=twin, name='S1')
    assert s.scenario_number == 'TSC-00001'
    assert s.is_runnable() is True


def test_oee_period_pct_math(acme):
    from apps.eam.models import Asset, AssetCategory
    cat = AssetCategory.objects.create(tenant=acme, code='C1', name='Cat')
    a = Asset.objects.create(tenant=acme, category=cat, tag='A1', name='Asset 1')
    p = I.OEEPeriod(
        tenant=acme, asset=a, period_date=date.today(),
        planned_run_minutes=Decimal('480'),
        run_minutes=Decimal('432'),
        ideal_cycle_seconds=Decimal('60'),
        total_count=Decimal('420'),
        good_count=Decimal('400'),
        scrap_count=Decimal('20'),
    )
    p.save()
    assert p.period_number == 'OEEP-00001'
    assert p.availability_pct == Decimal('90.00')
    # P = ideal_cycle * total_count / (run_minutes * 60) = 60 * 420 / (432 * 60) = ~97.22
    assert Decimal('95') < p.performance_pct <= Decimal('100')
    # Q = 400/420 = 95.24%
    assert Decimal('95') < p.quality_pct < Decimal('96')


def test_oee_period_zero_planned_safe(acme):
    from apps.eam.models import Asset, AssetCategory
    cat = AssetCategory.objects.create(tenant=acme, code='C2', name='Cat 2')
    a = Asset.objects.create(tenant=acme, category=cat, tag='A2', name='Asset 2')
    p = I.OEEPeriod(
        tenant=acme, asset=a, period_date=date.today(),
        planned_run_minutes=Decimal('0'),
        run_minutes=Decimal('0'),
        ideal_cycle_seconds=Decimal('60'),
        total_count=Decimal('0'),
    )
    p.save()
    assert p.availability_pct == Decimal('0')
    assert p.performance_pct == Decimal('0')
    assert p.quality_pct == Decimal('0')
    assert p.oee_pct == Decimal('0')


def test_state_log_duration_computed(acme):
    from apps.eam.models import Asset, AssetCategory
    cat = AssetCategory.objects.create(tenant=acme, code='C3', name='Cat 3')
    a = Asset.objects.create(tenant=acme, category=cat, tag='A3', name='Asset 3')
    now = timezone.now()
    log = I.MachineStateLog.objects.create(
        tenant=acme, asset=a, state='running',
        started_at=now - timedelta(minutes=10), ended_at=now,
        source='manual',
    )
    assert log.duration_seconds == 600


def test_anomaly_auto_number(acme, alert_rule, reading):
    d = I.AnomalyDetection.objects.create(
        tenant=acme, rule=alert_rule, source_reading=reading,
        value=Decimal('92.5'), severity='high', status='new',
    )
    assert d.detection_number == 'AD-00001'
    assert d.is_acknowledgeable() is True
    assert d.is_resolvable() is True
