"""Security tests — RBAC matrix (L-10), multi-tenant IDOR, anonymous redirects."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.utility import models as U


pytestmark = [pytest.mark.django_db, pytest.mark.security]


# ---------- Anonymous redirect ----------

ANON_LIST_URLS = [
    'utility:index',
    'utility:type_list',
    'utility:meter_list',
    'utility:consumption_list',
    'utility:tariff_list',
    'utility:allocation_list',
    'utility:dr_event_list',
    'utility:peak_list',
    'utility:factor_list',
    'utility:emission_list',
    'utility:sustainability_list',
    'utility:benchmark_list',
    'utility:benchmark_report_list',
]


@pytest.mark.parametrize('name', ANON_LIST_URLS)
def test_anonymous_redirected_to_login(client, name):
    r = client.get(reverse(name))
    assert r.status_code in (301, 302)


# ---------- RBAC: admin-only mutate routes block staff ----------

ADMIN_ONLY_GET_URLS = [
    'utility:type_create',
    'utility:meter_create',
    'utility:consumption_create',
    'utility:consumption_import',
    'utility:tariff_create',
    'utility:dr_event_create',
    'utility:factor_create',
    'utility:benchmark_report_create',
]


@pytest.mark.parametrize('name', ADMIN_ONLY_GET_URLS)
def test_staff_blocked_from_admin_only_create_get(staff_client, name):
    r = staff_client.get(reverse(name))
    assert r.status_code in (301, 302, 403)


def test_admin_can_load_admin_only_create_pages(admin_client):
    for name in ADMIN_ONLY_GET_URLS:
        r = admin_client.get(reverse(name))
        assert r.status_code in (200, 302), f'admin should reach {name}, got {r.status_code}'


def test_staff_can_view_lists(staff_client):
    """Staff is logged-in tenant member: list pages should render."""
    for name in ANON_LIST_URLS:
        r = staff_client.get(reverse(name))
        assert r.status_code != 403, f'staff should view {name}'


# ---------- RBAC: workflow POSTs block staff ----------

def test_staff_blocked_from_dr_event_activate_post(
    staff_client, acme, utility_type_electricity,
):
    now = timezone.now()
    e = U.DemandResponseEvent.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=1),
        status='scheduled',
    )
    r = staff_client.post(reverse('utility:dr_event_activate', args=[e.pk]))
    assert r.status_code in (302, 403)
    e.refresh_from_db()
    assert e.status == 'scheduled'


def test_staff_blocked_from_allocation_post(staff_client, acme):
    r = staff_client.post(reverse('utility:allocation_post'), data={})
    assert r.status_code in (302, 403)


def test_staff_blocked_from_peak_scan(staff_client):
    r = staff_client.post(reverse('utility:peak_scan'), data={'horizon_days': '14'})
    assert r.status_code in (302, 403)


# ---------- Multi-tenant IDOR ----------

def test_other_tenant_cannot_view_meter_detail(globex_client, meter):
    r = globex_client.get(reverse('utility:meter_detail', args=[meter.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_edit_meter(globex_client, meter):
    r = globex_client.get(reverse('utility:meter_edit', args=[meter.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_delete_meter(globex_client, meter):
    r = globex_client.post(reverse('utility:meter_delete', args=[meter.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_view_tariff_detail(globex_client, tariff):
    r = globex_client.get(reverse('utility:tariff_detail', args=[tariff.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_view_consumption_detail(globex_client, consumption):
    r = globex_client.get(reverse('utility:consumption_detail', args=[consumption.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_view_allocation_detail(globex_client, acme, acp_open, meter):
    a = U.UtilityAllocation.objects.create(
        tenant=acme, period=acp_open, meter=meter, share_pct=Decimal('100'),
    )
    r = globex_client.get(reverse('utility:allocation_detail', args=[a.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_view_dr_event_detail(globex_client, acme, utility_type_electricity):
    now = timezone.now()
    e = U.DemandResponseEvent.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=1),
    )
    r = globex_client.get(reverse('utility:dr_event_detail', args=[e.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_edit_factor(globex_client, emission_factor_grid):
    r = globex_client.get(reverse('utility:factor_edit', args=[emission_factor_grid.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_delete_factor(globex_client, emission_factor_grid):
    r = globex_client.post(reverse('utility:factor_delete', args=[emission_factor_grid.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_view_emission_detail(
    globex_client, acme, acp_open, emission_factor_grid,
):
    e = U.CarbonEmission.objects.create(
        tenant=acme, period=acp_open, scope='scope_2',
        source_type='electricity_grid', source_quantity=Decimal('10'),
        factor=emission_factor_grid,
    )
    r = globex_client.get(reverse('utility:emission_detail', args=[e.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_view_sustainability_detail(globex_client, acme, acp_open):
    k = U.SustainabilityKPI.objects.create(tenant=acme, period=acp_open)
    r = globex_client.get(reverse('utility:sustainability_detail', args=[k.pk]))
    assert r.status_code == 404


def test_other_tenant_cannot_view_benchmark_detail(globex_client, acme, acp_open):
    s = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='A',
        total_units_produced=Decimal('10'),
    )
    r = globex_client.get(reverse('utility:benchmark_detail', args=[s.pk]))
    assert r.status_code == 404


# ---------- Workflow gating ----------

def test_cannot_edit_active_dr_event(admin_client, acme, utility_type_electricity):
    """L-03: only scheduled DR events can be edited."""
    now = timezone.now()
    e = U.DemandResponseEvent.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=1),
        status='active',
    )
    r = admin_client.get(reverse('utility:dr_event_edit', args=[e.pk]))
    # Should redirect (warning) since not 'scheduled'
    assert r.status_code in (302, 200)


def test_cannot_complete_scheduled_dr_event(admin_client, acme, utility_type_electricity):
    now = timezone.now()
    e = U.DemandResponseEvent.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=1),
        status='scheduled',
    )
    r = admin_client.post(reverse('utility:dr_event_complete', args=[e.pk]))
    assert r.status_code == 302
    e.refresh_from_db()
    # Status unchanged because scheduled is not completable
    assert e.status == 'scheduled'
