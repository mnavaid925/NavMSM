"""Module 15 - form unit tests.

Covers L-01 (unique_together with tenant excluded), L-14 (per-workflow
required fields), and the AlertRule XOR scope validation.
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.iot import forms, models as I


pytestmark = pytest.mark.django_db


def test_broker_unique_name_per_tenant(acme, mqtt_protocol):
    I.DeviceBroker.objects.create(
        tenant=acme, name='B1', protocol=mqtt_protocol, host='h', port=1,
    )
    f = forms.DeviceBrokerForm(
        data={'name': 'B1', 'protocol': mqtt_protocol.pk, 'host': 'h2', 'port': 1, 'auth_method': 'none'},
        tenant=acme,
    )
    assert not f.is_valid()
    assert 'name' in f.errors


def test_alert_rule_xor_scope_zero_set_invalid(acme):
    f = forms.AlertRuleForm(
        data={
            'name': 'r1', 'condition_type': 'threshold_high',
            'threshold_high': '50', 'severity': 'medium',
            'notification_channels': 'in_app',
        },
        tenant=acme,
    )
    assert not f.is_valid()


def test_alert_rule_xor_scope_two_set_invalid(acme, temp_tag, device):
    f = forms.AlertRuleForm(
        data={
            'name': 'r1', 'device_tag': temp_tag.pk, 'scope_device': device.pk,
            'condition_type': 'threshold_high', 'threshold_high': '50',
            'severity': 'medium', 'notification_channels': 'in_app',
        },
        tenant=acme,
    )
    assert not f.is_valid()


def test_alert_rule_xor_scope_exactly_one_valid(acme, temp_tag):
    f = forms.AlertRuleForm(
        data={
            'name': 'r1', 'device_tag': temp_tag.pk,
            'condition_type': 'threshold_high', 'threshold_high': '50',
            'severity': 'medium', 'notification_channels': 'in_app',
            'window_seconds': 60, 'cooldown_seconds': 300,
        },
        tenant=acme,
    )
    assert f.is_valid(), f.errors


def test_alert_rule_threshold_high_required(acme, temp_tag):
    f = forms.AlertRuleForm(
        data={
            'name': 'r1', 'device_tag': temp_tag.pk,
            'condition_type': 'threshold_high', 'severity': 'medium',
            'notification_channels': 'in_app',
            'window_seconds': 60, 'cooldown_seconds': 300,
        },
        tenant=acme,
    )
    assert not f.is_valid()


def test_alert_rule_invalid_channel(acme, temp_tag):
    f = forms.AlertRuleForm(
        data={
            'name': 'r1', 'device_tag': temp_tag.pk,
            'condition_type': 'threshold_high', 'threshold_high': '50',
            'severity': 'medium', 'notification_channels': 'in_app,sms',
            'window_seconds': 60, 'cooldown_seconds': 300,
        },
        tenant=acme,
    )
    assert not f.is_valid()


def test_anomaly_resolve_form_requires_notes():
    f = forms.AnomalyResolveForm(data={'resolution_notes': '   '})
    assert not f.is_valid()


def test_anomaly_resolve_form_accepts_notes():
    f = forms.AnomalyResolveForm(data={'resolution_notes': 'Replaced sensor.'})
    assert f.is_valid()


def test_anomaly_false_positive_form_requires_notes():
    f = forms.AnomalyFalsePositiveForm(data={'resolution_notes': ''})
    assert not f.is_valid()


def test_oee_form_good_plus_scrap_le_total(acme, temp_tag):
    from apps.eam.models import Asset, AssetCategory
    cat = AssetCategory.objects.create(tenant=acme, code='C1', name='C')
    a = Asset.objects.create(tenant=acme, category=cat, tag='A1', name='A')
    f = forms.OEEPeriodForm(
        data={
            'asset': a.pk, 'period_date': '2026-05-10',
            'planned_run_minutes': '480', 'run_minutes': '450',
            'ideal_cycle_seconds': '60', 'total_count': '100',
            'good_count': '95', 'scrap_count': '20',
        },
        tenant=acme,
    )
    assert not f.is_valid()


def test_iot_reading_requires_one_value(acme, temp_tag):
    f = forms.IoTReadingForm(
        data={
            'device_tag': temp_tag.pk,
            'timestamp': '2026-05-10T08:00',
            'quality': 'good', 'source': 'manual',
        },
        tenant=acme,
    )
    assert not f.is_valid()


def test_device_tag_unique_address(acme, device):
    I.DeviceTag.objects.create(
        tenant=acme, device=device, name='t1', address='a/b', data_type='float',
    )
    f = forms.DeviceTagForm(
        data={
            'name': 't2', 'device': device.pk, 'address': 'a/b',
            'data_type': 'float', 'scale_factor': '1', 'offset': '0',
            'sampling_interval_seconds': 60, 'is_active': True,
        },
        tenant=acme,
    )
    assert not f.is_valid()
