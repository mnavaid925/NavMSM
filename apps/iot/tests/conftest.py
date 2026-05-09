"""Shared fixtures for the IoT & SCADA Integration test suite."""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant, set_current_tenant
from apps.iot import models as I


@pytest.fixture(autouse=True)
def _clear_tenant():
    yield
    set_current_tenant(None)


@pytest.fixture
def acme(db):
    return Tenant.objects.create(name='Acme IoT', slug='acme-iot-test', is_active=True)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex IoT', slug='globex-iot-test', is_active=True)


@pytest.fixture
def acme_admin(db, acme):
    return User.objects.create_user(
        username='admin_acme_iot', password='pw', tenant=acme,
        is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def acme_staff(db, acme):
    return User.objects.create_user(
        username='staff_acme_iot', password='pw', tenant=acme,
        is_tenant_admin=False, role='operator',
    )


@pytest.fixture
def globex_admin(db, globex):
    return User.objects.create_user(
        username='admin_globex_iot', password='pw', tenant=globex,
        is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def admin_client(client, acme_admin):
    client.force_login(acme_admin)
    return client


@pytest.fixture
def staff_client(client, acme_staff):
    client.force_login(acme_staff)
    return client


@pytest.fixture
def globex_client(client, globex_admin):
    client.force_login(globex_admin)
    return client


@pytest.fixture
def mqtt_protocol(db):
    return I.DeviceProtocol.objects.create(code='mqtt', name='MQTT', default_port=1883)


@pytest.fixture
def broker(db, acme, mqtt_protocol):
    return I.DeviceBroker.objects.create(
        tenant=acme, name='Test MQTT', protocol=mqtt_protocol,
        host='broker.test', port=1883, status='active',
    )


@pytest.fixture
def device(db, acme, broker, mqtt_protocol):
    return I.Device.objects.create(
        tenant=acme, name='Test Device', broker=broker, protocol=mqtt_protocol,
        device_type='sensor_node', status='active',
    )


@pytest.fixture
def temp_tag(db, acme, device):
    return I.DeviceTag.objects.create(
        tenant=acme, device=device, name='temperature', address='plant/test/temp',
        data_type='float', unit='C', is_active=True,
    )


@pytest.fixture
def alert_rule(db, acme, temp_tag):
    return I.AlertRule.objects.create(
        tenant=acme, name='High Temp', device_tag=temp_tag,
        condition_type='threshold_high', threshold_high=Decimal('80'),
        severity='high', notification_channels='in_app', is_active=True,
    )


@pytest.fixture
def reading(db, acme, temp_tag):
    return I.IoTReading.objects.create(
        tenant=acme, device_tag=temp_tag, timestamp=timezone.now(),
        value_numeric=Decimal('72.5'), quality='good', source='manual',
    )
