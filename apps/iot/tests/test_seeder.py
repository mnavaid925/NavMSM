"""Module 15 - seed_iot management command regression tests.

Verifies the seeder is idempotent and produces the expected fixture counts.
"""
import pytest
from django.core.management import call_command


pytestmark = pytest.mark.django_db


def test_seed_creates_protocols(acme):
    call_command('seed_iot', tenant=acme.slug)
    from apps.iot.models import DeviceProtocol
    assert DeviceProtocol.objects.count() >= 6


def test_seed_creates_brokers_per_tenant(acme):
    call_command('seed_iot', tenant=acme.slug)
    from apps.iot.models import DeviceBroker
    assert DeviceBroker.objects.filter(tenant=acme).count() == 2


def test_seed_creates_devices_per_tenant(acme):
    call_command('seed_iot', tenant=acme.slug)
    from apps.iot.models import Device
    # Up to 6 devices; depends on whether any seeded eam.Asset rows exist.
    assert Device.objects.filter(tenant=acme).count() == 6


def test_seed_creates_tags(acme):
    call_command('seed_iot', tenant=acme.slug)
    from apps.iot.models import DeviceTag
    # 5 tags per device * 6 devices = 30
    assert DeviceTag.objects.filter(tenant=acme).count() == 30


def test_seed_creates_alert_rules(acme):
    call_command('seed_iot', tenant=acme.slug)
    from apps.iot.models import AlertRule
    assert AlertRule.objects.filter(tenant=acme).count() == 4


def test_seed_creates_loss_reasons(acme):
    call_command('seed_iot', tenant=acme.slug)
    from apps.iot.models import LossReason
    assert LossReason.objects.filter(tenant=acme).count() == 5


def test_seed_creates_readings(acme):
    call_command('seed_iot', tenant=acme.slug)
    from apps.iot.models import IoTReading
    # 5h * 4 tags * 6 devices + 2 anomalies = 122
    n = IoTReading.objects.filter(tenant=acme).count()
    assert n >= 100


def test_seed_creates_anomalous_readings(acme):
    call_command('seed_iot', tenant=acme.slug)
    from apps.iot.models import IoTReading
    from decimal import Decimal
    # The 92.5C and 15.2 mm/s outliers
    big = IoTReading.objects.filter(
        tenant=acme, value_numeric__gte=Decimal('90'),
    ).count()
    assert big >= 1


def test_seed_creates_twins(acme):
    call_command('seed_iot', tenant=acme.slug)
    from apps.iot.models import DigitalTwin
    assert DigitalTwin.objects.filter(tenant=acme).count() == 3


def test_seed_creates_oee_periods(acme):
    call_command('seed_iot', tenant=acme.slug)
    from apps.iot.models import OEEPeriod
    # 7 days * 3 assets = 21 (depends on assets seeded)
    assert OEEPeriod.objects.filter(tenant=acme).count() >= 1


def test_seed_idempotent(acme):
    call_command('seed_iot', tenant=acme.slug)
    from apps.iot.models import Device
    first = Device.objects.filter(tenant=acme).count()
    # Second run must skip per the existence guard.
    call_command('seed_iot', tenant=acme.slug)
    assert Device.objects.filter(tenant=acme).count() == first


def test_seed_flush_resets(acme):
    call_command('seed_iot', tenant=acme.slug)
    from apps.iot.models import Device
    first = Device.objects.filter(tenant=acme).count()
    call_command('seed_iot', tenant=acme.slug, flush=True)
    second = Device.objects.filter(tenant=acme).count()
    assert second == first  # identical fixture re-built
