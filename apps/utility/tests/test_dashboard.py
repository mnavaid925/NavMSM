"""Dashboard KPI cards + ApexCharts series shape (L-07: json_script payload)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.utility import models as U


pytestmark = pytest.mark.django_db


def test_dashboard_renders_for_admin(admin_client):
    r = admin_client.get(reverse('utility:index'))
    assert r.status_code == 200


def test_dashboard_renders_for_staff(staff_client):
    """Read-only dashboard surface should be available to all tenant users."""
    r = staff_client.get(reverse('utility:index'))
    assert r.status_code == 200


def test_dashboard_kpi_context_has_required_keys(admin_client):
    r = admin_client.get(reverse('utility:index'))
    assert r.status_code == 200
    kpi = r.context['kpi']
    for key in (
        'meter_count', 'open_dr_events', 'open_suggestions',
        'open_allocations', 'posted_allocations',
        'period_kwh', 'period_co2e',
    ):
        assert key in kpi, f'Missing KPI key: {key}'


def test_dashboard_chart_context_is_list_of_dicts(admin_client, acme, acp_open):
    """L-07: chart_series in context must be raw Python list[dict] (not pre-serialized JSON)."""
    U.SustainabilityKPI.objects.create(
        tenant=acme, period=acp_open,
        total_scope_1_kg=Decimal('10'),
        total_scope_2_kg=Decimal('20'),
        total_scope_3_kg=Decimal('30'),
        total_kwh=Decimal('100'),
        total_water_m3=Decimal('5'),
        total_gas_m3=Decimal('3'),
        total_units_produced=Decimal('10'),
    )
    r = admin_client.get(reverse('utility:index'))
    assert r.status_code == 200
    consumption_chart = r.context['consumption_chart']
    assert isinstance(consumption_chart, list)
    assert all(isinstance(row, dict) for row in consumption_chart)
    assert len(consumption_chart) == 1
    assert {'period', 'kwh', 'water', 'gas'} <= set(consumption_chart[0].keys())

    co2e_chart = r.context['co2e_chart']
    assert isinstance(co2e_chart, list)
    assert all(isinstance(row, dict) for row in co2e_chart)
    assert {'period', 'scope_1', 'scope_2', 'scope_3'} <= set(co2e_chart[0].keys())


def test_dashboard_emits_json_script_blocks(admin_client):
    """L-07: dashboard template wraps chart series via Django json_script tag."""
    r = admin_client.get(reverse('utility:index'))
    assert r.status_code == 200
    body = r.content.decode('utf-8', errors='ignore')
    # json_script renders `<script type="application/json" id="...">`
    assert 'consumption-chart-data' in body
    assert 'co2e-chart-data' in body


def test_dashboard_meter_count_reflects_active_meters(admin_client, acme, meter):
    r = admin_client.get(reverse('utility:index'))
    assert r.status_code == 200
    # meter fixture is active by default
    assert r.context['kpi']['meter_count'] >= 1


def test_dashboard_open_dr_events_count(admin_client, acme, utility_type_electricity):
    now = timezone.now()
    U.DemandResponseEvent.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=1),
        status='scheduled',
    )
    r = admin_client.get(reverse('utility:index'))
    assert r.context['kpi']['open_dr_events'] == 1


def test_dashboard_period_kwh_aggregates_consumption(
    admin_client, acme, meter, utility_type_electricity,
):
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    U.UtilityConsumption.objects.create(
        tenant=acme, meter=meter,
        period_start=month_start + timedelta(hours=1),
        period_end=month_start + timedelta(hours=2),
        start_reading=Decimal('0'), end_reading=Decimal('100'),
        unit_cost=Decimal('0.10'),
    )
    r = admin_client.get(reverse('utility:index'))
    assert r.context['kpi']['period_kwh'] >= Decimal('100')
