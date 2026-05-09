"""Module 15 - view smoke tests.

Covers:
    * dashboard renders
    * list views render
    * cross-tenant 404
    * anonymous redirect to login
    * RBAC: staff blocked from mutate URLs
"""
import pytest
from django.urls import reverse


pytestmark = pytest.mark.django_db


def test_dashboard_admin(admin_client):
    r = admin_client.get(reverse('iot:index'))
    assert r.status_code == 200


def test_dashboard_anonymous_redirects(client):
    r = client.get(reverse('iot:index'))
    assert r.status_code in (302, 403)


def test_protocol_list_admin(admin_client, mqtt_protocol):
    r = admin_client.get(reverse('iot:protocol_list'))
    assert r.status_code == 200


def test_broker_list_admin(admin_client, broker):
    r = admin_client.get(reverse('iot:broker_list'))
    assert r.status_code == 200
    assert broker.broker_number.encode() in r.content


def test_device_list_admin(admin_client, device):
    r = admin_client.get(reverse('iot:device_list'))
    assert r.status_code == 200


def test_tag_list_admin(admin_client, temp_tag):
    r = admin_client.get(reverse('iot:tag_list'))
    assert r.status_code == 200


def test_reading_list_admin(admin_client, reading):
    r = admin_client.get(reverse('iot:reading_list'))
    assert r.status_code == 200


def test_twin_list_admin(admin_client):
    r = admin_client.get(reverse('iot:twin_list'))
    assert r.status_code == 200


def test_oee_dashboard_admin(admin_client):
    r = admin_client.get(reverse('iot:oee_dashboard'))
    assert r.status_code == 200


def test_alert_rules_list_admin(admin_client, alert_rule):
    r = admin_client.get(reverse('iot:rule_list'))
    assert r.status_code == 200


def test_anomaly_list_admin(admin_client):
    r = admin_client.get(reverse('iot:detection_list'))
    assert r.status_code == 200


def test_cross_tenant_device_404(globex_client, device):
    r = globex_client.get(reverse('iot:device_detail', args=[device.pk]))
    assert r.status_code == 404


def test_cross_tenant_broker_404(globex_client, broker):
    r = globex_client.get(reverse('iot:broker_detail', args=[broker.pk]))
    assert r.status_code == 404


def test_staff_blocked_from_device_create(staff_client):
    r = staff_client.post(reverse('iot:device_create'))
    assert r.status_code in (302, 403)


def test_staff_blocked_from_rule_delete(staff_client, alert_rule):
    r = staff_client.post(reverse('iot:rule_delete', args=[alert_rule.pk]))
    assert r.status_code in (302, 403)
    from apps.iot.models import AlertRule
    # Rule not deleted.
    assert AlertRule.objects.filter(pk=alert_rule.pk).exists()


def test_anonymous_blocked_from_reading_delete(client, reading):
    r = client.post(reverse('iot:reading_delete', args=[reading.pk]))
    assert r.status_code in (302, 403)
    from apps.iot.models import IoTReading
    assert IoTReading.objects.filter(pk=reading.pk).exists()
