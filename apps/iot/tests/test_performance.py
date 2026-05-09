"""Module 15 - performance tests.

Verifies N+1 query budget on dashboard and key list views. Uses
``django.test.utils.CaptureQueriesContext`` style via ``assertNumQueries``.
"""
from decimal import Decimal

import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone


pytestmark = pytest.mark.django_db


def _seed_readings(acme, temp_tag, n=10):
    from apps.iot import models as I
    for i in range(n):
        I.IoTReading.objects.create(
            tenant=acme, device_tag=temp_tag,
            value_numeric=Decimal('70') + Decimal(i),
            timestamp=timezone.now(), quality='good', source='manual',
        )


def test_dashboard_query_budget(admin_client, acme, temp_tag):
    _seed_readings(acme, temp_tag, n=15)
    with CaptureQueriesContext(connection) as ctx:
        r = admin_client.get(reverse('iot:index'))
    assert r.status_code == 200
    # Empirical budget: ~30-40 queries (auth, tenant lookup, KPI counts,
    # recent readings + anomalies, OEE chart aggregation, anomaly chart).
    # 60 is a conservative ceiling — flag any regression > 60.
    assert len(ctx.captured_queries) < 60


def test_reading_list_query_budget(admin_client, acme, temp_tag):
    _seed_readings(acme, temp_tag, n=30)
    with CaptureQueriesContext(connection) as ctx:
        r = admin_client.get(reverse('iot:reading_list'))
    assert r.status_code == 200
    # select_related on device_tag + device + batch should keep this <= 25.
    assert len(ctx.captured_queries) < 30


def test_device_list_query_budget(admin_client, acme, broker, mqtt_protocol):
    from apps.iot import models as I
    for i in range(20):
        I.Device.objects.create(
            tenant=acme, name=f'D{i}', broker=broker, protocol=mqtt_protocol,
            device_type='sensor_node', status='active',
        )
    with CaptureQueriesContext(connection) as ctx:
        r = admin_client.get(reverse('iot:device_list'))
    assert r.status_code == 200
    assert len(ctx.captured_queries) < 30


def test_alert_rules_list_query_budget(admin_client, acme, temp_tag):
    from apps.iot import models as I
    for i in range(15):
        I.AlertRule.objects.create(
            tenant=acme, name=f'r{i}', device_tag=temp_tag,
            condition_type='threshold_high', threshold_high=Decimal('80'),
            severity='medium', notification_channels='in_app',
        )
    with CaptureQueriesContext(connection) as ctx:
        r = admin_client.get(reverse('iot:rule_list'))
    assert r.status_code == 200
    assert len(ctx.captured_queries) < 30


def test_anomaly_list_query_budget(admin_client, acme, alert_rule, temp_tag):
    from apps.iot import models as I
    # Pre-create source readings
    readings = []
    for i in range(10):
        readings.append(I.IoTReading.objects.create(
            tenant=acme, device_tag=temp_tag, value_numeric=Decimal(80 + i),
            timestamp=timezone.now(), quality='good', source='manual',
        ))
    # Pre-create detections (bypassing signals to control fixture)
    for r in readings:
        I.AnomalyDetection.objects.get_or_create(
            tenant=acme, rule=alert_rule, source_reading=r,
            defaults={'severity': 'medium', 'status': 'new'},
        )
    with CaptureQueriesContext(connection) as ctx:
        r = admin_client.get(reverse('iot:detection_list'))
    assert r.status_code == 200
    assert len(ctx.captured_queries) < 30
