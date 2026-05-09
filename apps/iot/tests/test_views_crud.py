"""Module 15 - CRUD-path view tests.

Cycles each major resource through Create / Edit / Delete via the HTTP layer,
verifying the form roundtrip works end-to-end (including the L-01 unique
constraints and the AlertRule XOR scope).
"""
from decimal import Decimal

import pytest
from django.urls import reverse


pytestmark = pytest.mark.django_db


# -- Protocol (shared catalog, no tenant) --------------------------------

def test_protocol_create_via_form(admin_client):
    r = admin_client.post(reverse('iot:protocol_create'),
                          data={'code': 'mqtt5', 'name': 'MQTT 5', 'default_port': 8883, 'is_active': 'on'})
    assert r.status_code == 302
    from apps.iot.models import DeviceProtocol
    assert DeviceProtocol.objects.filter(code='mqtt5').exists()


def test_protocol_create_duplicate_code_blocked(admin_client, mqtt_protocol):
    r = admin_client.post(reverse('iot:protocol_create'),
                          data={'code': 'mqtt', 'name': 'Dup', 'default_port': 1883, 'is_active': 'on'})
    assert r.status_code == 200  # re-renders with errors
    from apps.iot.models import DeviceProtocol
    assert DeviceProtocol.objects.filter(code='mqtt').count() == 1


# -- Broker --------------------------------------------------------------

def test_broker_create(admin_client, acme, mqtt_protocol):
    r = admin_client.post(reverse('iot:broker_create'),
                          data={'name': 'New Broker', 'protocol': mqtt_protocol.pk,
                                'host': 'h.example', 'port': 1883, 'auth_method': 'none'})
    assert r.status_code == 302
    from apps.iot.models import DeviceBroker
    assert DeviceBroker.objects.filter(tenant=acme, name='New Broker').exists()


def test_broker_edit_renames(admin_client, broker):
    r = admin_client.post(reverse('iot:broker_edit', args=[broker.pk]),
                          data={'name': 'Renamed', 'protocol': broker.protocol_id,
                                'host': broker.host, 'port': broker.port,
                                'auth_method': broker.auth_method})
    assert r.status_code == 302
    broker.refresh_from_db()
    assert broker.name == 'Renamed'


def test_broker_delete(admin_client, broker):
    r = admin_client.post(reverse('iot:broker_delete', args=[broker.pk]))
    assert r.status_code == 302
    from apps.iot.models import DeviceBroker
    assert not DeviceBroker.objects.filter(pk=broker.pk).exists()


# -- Device --------------------------------------------------------------

def test_device_create(admin_client, acme, broker, mqtt_protocol):
    r = admin_client.post(reverse('iot:device_create'),
                          data={'name': 'NewDev', 'broker': broker.pk,
                                'protocol': mqtt_protocol.pk, 'device_type': 'plc'})
    assert r.status_code == 302
    from apps.iot.models import Device
    assert Device.objects.filter(name='NewDev', tenant=acme).exists()


def test_device_create_duplicate_name_blocked(admin_client, acme, broker, mqtt_protocol):
    from apps.iot.models import Device
    Device.objects.create(tenant=acme, name='Dup', broker=broker, protocol=mqtt_protocol)
    r = admin_client.post(reverse('iot:device_create'),
                          data={'name': 'Dup', 'broker': broker.pk,
                                'protocol': mqtt_protocol.pk, 'device_type': 'plc'})
    assert r.status_code == 200  # re-render with errors
    assert Device.objects.filter(tenant=acme, name='Dup').count() == 1


# -- Tag -----------------------------------------------------------------

def test_tag_create(admin_client, acme, device):
    r = admin_client.post(reverse('iot:tag_create'),
                          data={'name': 'pressure', 'device': device.pk,
                                'address': 'plant/x/p', 'data_type': 'float',
                                'scale_factor': '1.0', 'offset': '0',
                                'sampling_interval_seconds': 60, 'is_active': 'on'})
    assert r.status_code == 302
    from apps.iot.models import DeviceTag
    assert DeviceTag.objects.filter(name='pressure', tenant=acme).exists()


# -- AlertRule XOR validation via form roundtrip ------------------------

def test_alert_rule_form_zero_scope_rejected(admin_client, acme):
    r = admin_client.post(reverse('iot:rule_create'),
                          data={'name': 'NoScope', 'condition_type': 'threshold_high',
                                'threshold_high': '99', 'severity': 'medium',
                                'notification_channels': 'in_app',
                                'window_seconds': 60, 'cooldown_seconds': 300})
    assert r.status_code == 200  # form re-rendered
    from apps.iot.models import AlertRule
    assert not AlertRule.objects.filter(name='NoScope').exists()


def test_alert_rule_form_two_scopes_rejected(admin_client, acme, temp_tag, device):
    r = admin_client.post(reverse('iot:rule_create'),
                          data={'name': 'TwoScopes', 'device_tag': temp_tag.pk,
                                'scope_device': device.pk,
                                'condition_type': 'threshold_high',
                                'threshold_high': '99', 'severity': 'medium',
                                'notification_channels': 'in_app',
                                'window_seconds': 60, 'cooldown_seconds': 300})
    assert r.status_code == 200
    from apps.iot.models import AlertRule
    assert not AlertRule.objects.filter(name='TwoScopes').exists()


def test_alert_rule_form_one_scope_accepted(admin_client, acme, temp_tag):
    r = admin_client.post(reverse('iot:rule_create'),
                          data={'name': 'OneScope', 'device_tag': temp_tag.pk,
                                'condition_type': 'threshold_high',
                                'threshold_high': '99', 'severity': 'medium',
                                'notification_channels': 'in_app',
                                'window_seconds': 60, 'cooldown_seconds': 300})
    assert r.status_code == 302
    from apps.iot.models import AlertRule
    assert AlertRule.objects.filter(tenant=acme, name='OneScope').exists()


# -- LossReason CRUD -----------------------------------------------------

def test_loss_reason_create(admin_client, acme):
    r = admin_client.post(reverse('iot:loss_reason_create'),
                          data={'code': 'STARTUP', 'name': 'Startup Loss',
                                'category': 'availability', 'is_active': 'on'})
    assert r.status_code == 302
    from apps.iot.models import LossReason
    assert LossReason.objects.filter(tenant=acme, code='STARTUP').exists()


def test_loss_reason_duplicate_code_rejected(admin_client, acme):
    from apps.iot.models import LossReason
    LossReason.objects.create(tenant=acme, code='DUP', name='dup', category='availability')
    r = admin_client.post(reverse('iot:loss_reason_create'),
                          data={'code': 'DUP', 'name': 'dup2', 'category': 'availability', 'is_active': 'on'})
    assert r.status_code == 200
    assert LossReason.objects.filter(tenant=acme, code='DUP').count() == 1


# -- IoT Reading manual entry -------------------------------------------

def test_reading_manual_create_requires_one_value(admin_client, temp_tag):
    r = admin_client.post(reverse('iot:reading_create'),
                          data={'device_tag': temp_tag.pk,
                                'timestamp': '2026-05-10 08:00:00',
                                'quality': 'good', 'source': 'manual'})
    # Form requires one of value_numeric/value_text/value_bool
    assert r.status_code == 200


def test_reading_manual_create_with_value(admin_client, temp_tag, acme):
    r = admin_client.post(reverse('iot:reading_create'),
                          data={'device_tag': temp_tag.pk,
                                'timestamp': '2026-05-10 08:00:00',
                                'value_numeric': '72.5',
                                'quality': 'good', 'source': 'manual'})
    assert r.status_code == 302
    from apps.iot.models import IoTReading
    assert IoTReading.objects.filter(tenant=acme, value_numeric=Decimal('72.5')).exists()


# -- Bulk ingest endpoint ----------------------------------------------

def test_bulk_ingest_json(admin_client, temp_tag, acme):
    payload = (
        '[{"tag_address": "%s", "timestamp": "2026-05-10T08:00:00", "value": 70.1},'
        ' {"tag_address": "%s", "timestamp": "2026-05-10T08:01:00", "value": 71.2}]'
    ) % (temp_tag.address, temp_tag.address)
    r = admin_client.post(reverse('iot:reading_ingest'),
                          data={'payload': payload, 'source_format': 'json'})
    assert r.status_code == 302
    from apps.iot.models import IoTReading, IoTReadingBatch
    assert IoTReadingBatch.objects.filter(tenant=acme).exists()
    assert IoTReading.objects.filter(tenant=acme, source='replay').count() == 2


def test_bulk_ingest_invalid_tag(admin_client, acme):
    payload = '[{"tag_address": "no/such/tag", "timestamp": "2026-05-10T08:00:00", "value": 70}]'
    r = admin_client.post(reverse('iot:reading_ingest'),
                          data={'payload': payload, 'source_format': 'json'})
    # Goes to detail page on partial / failed
    assert r.status_code in (200, 302)
    from apps.iot.models import IoTReading
    assert IoTReading.objects.filter(tenant=acme, source='replay').count() == 0


def test_bulk_ingest_malformed_json(admin_client):
    r = admin_client.post(reverse('iot:reading_ingest'),
                          data={'payload': 'not-json', 'source_format': 'json'})
    assert r.status_code == 200
