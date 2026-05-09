"""Module 15 - signal cascade tests.

Covers:
    * IoTReading.post_save -> StreamMetric refresh
    * IoTReading.post_save -> AnomalyDetection (threshold rule)
    * AnomalyDetection.post_save -> AlertNotification per channel
    * Idempotency: re-fired post_save does not double-write
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.iot import models as I


pytestmark = pytest.mark.django_db


def test_iot_reading_creates_stream_metric(acme, temp_tag):
    I.IoTReading.objects.create(
        tenant=acme, device_tag=temp_tag, value_numeric=Decimal('72'),
        timestamp=timezone.now(), quality='good', source='manual',
    )
    sm = I.StreamMetric.objects.get(tenant=acme, device_tag=temp_tag)
    assert sm.latest_value == Decimal('72')
    assert sm.count_24h == 1


def test_iot_reading_updates_stream_metric_aggregates(acme, temp_tag):
    for v in [Decimal('70'), Decimal('72'), Decimal('74')]:
        I.IoTReading.objects.create(
            tenant=acme, device_tag=temp_tag, value_numeric=v,
            timestamp=timezone.now(), quality='good', source='manual',
        )
    sm = I.StreamMetric.objects.get(tenant=acme, device_tag=temp_tag)
    assert sm.latest_value == Decimal('74')
    assert sm.last_24h_min == Decimal('70')
    assert sm.last_24h_max == Decimal('74')
    assert sm.last_24h_avg == Decimal('72.0000')
    assert sm.count_24h == 3


def test_iot_reading_fires_anomaly_when_above_threshold(acme, alert_rule, temp_tag):
    r = I.IoTReading.objects.create(
        tenant=acme, device_tag=temp_tag, value_numeric=Decimal('92'),
        timestamp=timezone.now(), quality='good', source='manual',
    )
    detections = I.AnomalyDetection.objects.filter(rule=alert_rule, source_reading=r)
    assert detections.count() == 1
    d = detections.first()
    assert d.severity == 'high'
    assert d.value == Decimal('92')


def test_iot_reading_below_threshold_no_anomaly(acme, alert_rule, temp_tag):
    r = I.IoTReading.objects.create(
        tenant=acme, device_tag=temp_tag, value_numeric=Decimal('72'),
        timestamp=timezone.now(), quality='good', source='manual',
    )
    detections = I.AnomalyDetection.objects.filter(rule=alert_rule, source_reading=r)
    assert detections.count() == 0


def test_anomaly_idempotent_when_resaved(acme, alert_rule, temp_tag):
    r = I.IoTReading.objects.create(
        tenant=acme, device_tag=temp_tag, value_numeric=Decimal('92'),
        timestamp=timezone.now(), quality='good', source='manual',
    )
    initial = I.AnomalyDetection.objects.count()
    r.notes = 'edited'
    r.save()
    assert I.AnomalyDetection.objects.count() == initial


def test_anomaly_creates_notifications_per_channel(acme, alert_rule, temp_tag):
    alert_rule.notification_channels = 'in_app,email,mes_andon'
    alert_rule.save(update_fields=['notification_channels'])
    I.IoTReading.objects.create(
        tenant=acme, device_tag=temp_tag, value_numeric=Decimal('92'),
        timestamp=timezone.now(), quality='good', source='manual',
    )
    notifications = I.AlertNotification.objects.filter(detection__rule=alert_rule)
    channels = set(notifications.values_list('channel', flat=True))
    assert channels == {'in_app', 'email', 'mes_andon'}


def test_inactive_rule_does_not_fire(acme, alert_rule, temp_tag):
    alert_rule.is_active = False
    alert_rule.save(update_fields=['is_active'])
    I.IoTReading.objects.create(
        tenant=acme, device_tag=temp_tag, value_numeric=Decimal('92'),
        timestamp=timezone.now(), quality='good', source='manual',
    )
    assert I.AnomalyDetection.objects.count() == 0


def test_cooldown_suppresses_duplicate_detection(acme, alert_rule, temp_tag):
    alert_rule.cooldown_seconds = 600
    alert_rule.save(update_fields=['cooldown_seconds'])
    I.IoTReading.objects.create(
        tenant=acme, device_tag=temp_tag, value_numeric=Decimal('92'),
        timestamp=timezone.now(), quality='good', source='manual',
    )
    I.IoTReading.objects.create(
        tenant=acme, device_tag=temp_tag, value_numeric=Decimal('95'),
        timestamp=timezone.now(), quality='good', source='manual',
    )
    # Cooldown means only the first reading fires.
    assert I.AnomalyDetection.objects.count() == 1
