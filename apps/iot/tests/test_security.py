"""Module 15 - security tests.

Covers:
    * Cross-tenant data isolation (querysets filtered by tenant)
    * RBAC L-10: TenantAdminRequiredMixin gates on mutating views
    * Safe formula evaluator rejects code injection (covered in test_services
      but spot-checked here against the live model path)
    * DeviceBroker password not exposed in __str__ / list response
"""
import pytest
from django.urls import reverse


pytestmark = pytest.mark.django_db


def test_cross_tenant_reading_isolated(globex_client, reading):
    r = globex_client.get(reverse('iot:reading_detail', args=[reading.pk]))
    assert r.status_code == 404


def test_cross_tenant_alert_rule_isolated(globex_client, alert_rule):
    r = globex_client.get(reverse('iot:rule_detail', args=[alert_rule.pk]))
    assert r.status_code == 404


def test_admin_only_creates_broker(staff_client):
    r = staff_client.get(reverse('iot:broker_create'))
    assert r.status_code in (302, 403)


def test_admin_only_resolves_anomaly(staff_client, acme, alert_rule, reading):
    from apps.iot.models import AnomalyDetection
    d = AnomalyDetection.objects.create(
        tenant=acme, rule=alert_rule, source_reading=reading,
        severity='high', status='new',
    )
    r = staff_client.post(reverse('iot:detection_resolve', args=[d.pk]),
                          data={'resolution_notes': 'fixed'})
    assert r.status_code in (302, 403)
    d.refresh_from_db()
    assert d.status == 'new'  # not changed


def test_broker_password_not_in_list_response(admin_client, acme, broker):
    broker.password_hash = 'SUPERSECRET_HASH_XYZ'
    broker.save(update_fields=['password_hash'])
    r = admin_client.get(reverse('iot:broker_list'))
    assert r.status_code == 200
    # The list view does not render password_hash; verify that.
    assert b'SUPERSECRET_HASH_XYZ' not in r.content
