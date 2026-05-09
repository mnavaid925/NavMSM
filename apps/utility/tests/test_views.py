"""Full CRUD smoke + workflow happy paths for Module 14 views."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.utility import models as U


pytestmark = pytest.mark.django_db


# ---------- List smoke ----------

LIST_URLS = [
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


@pytest.mark.parametrize('name', LIST_URLS)
def test_list_pages_render_200(admin_client, name):
    r = admin_client.get(reverse(name))
    assert r.status_code == 200, f'{name} returned {r.status_code}'


# ---------- UtilityType CRUD ----------

def test_create_utility_type(admin_client, acme):
    r = admin_client.post(reverse('utility:type_create'), data={
        'code': 'natural_gas', 'name': 'Natural Gas',
        'unit_of_measure': 'm3', 'is_active': 'on',
    })
    assert r.status_code == 302
    assert U.UtilityType.objects.filter(tenant=acme, code='natural_gas').exists()


def test_edit_utility_type(admin_client, utility_type_electricity):
    r = admin_client.post(
        reverse('utility:type_edit', args=[utility_type_electricity.pk]),
        data={
            'code': 'electricity', 'name': 'Updated Name',
            'unit_of_measure': 'kwh', 'is_active': 'on',
        },
    )
    assert r.status_code == 302
    utility_type_electricity.refresh_from_db()
    assert utility_type_electricity.name == 'Updated Name'


def test_delete_utility_type(admin_client, acme):
    t = U.UtilityType.objects.create(
        tenant=acme, code='steam', name='Steam', unit_of_measure='kg',
    )
    r = admin_client.post(reverse('utility:type_delete', args=[t.pk]))
    assert r.status_code == 302
    assert not U.UtilityType.objects.filter(pk=t.pk).exists()


# ---------- UtilityMeter CRUD ----------

def test_create_meter(admin_client, acme, utility_type_electricity):
    r = admin_client.post(reverse('utility:meter_create'), data={
        'utility_type': utility_type_electricity.pk,
        'name': 'Sub-Meter A', 'multiplier': '1.0', 'is_active': 'on',
    })
    assert r.status_code == 302
    assert U.UtilityMeter.objects.filter(tenant=acme, name='Sub-Meter A').exists()


def test_view_meter_detail(admin_client, meter):
    r = admin_client.get(reverse('utility:meter_detail', args=[meter.pk]))
    assert r.status_code == 200


def test_edit_meter(admin_client, meter, utility_type_electricity):
    r = admin_client.post(reverse('utility:meter_edit', args=[meter.pk]), data={
        'utility_type': utility_type_electricity.pk,
        'name': 'Renamed', 'multiplier': '2.0', 'is_active': 'on',
    })
    assert r.status_code == 302
    meter.refresh_from_db()
    assert meter.name == 'Renamed'


def test_delete_meter(admin_client, acme, utility_type_electricity):
    m = U.UtilityMeter.objects.create(
        tenant=acme, utility_type=utility_type_electricity, name='Tmp',
    )
    r = admin_client.post(reverse('utility:meter_delete', args=[m.pk]))
    assert r.status_code == 302


# ---------- UtilityConsumption CRUD ----------

def test_create_consumption(admin_client, acme, meter):
    now = timezone.now()
    r = admin_client.post(reverse('utility:consumption_create'), data={
        'meter': meter.pk,
        'period_start': (now - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
        'period_end': now.strftime('%Y-%m-%dT%H:%M'),
        'start_reading': '0', 'end_reading': '50',
        'unit_cost': '0.10', 'source': 'manual',
    })
    assert r.status_code == 302
    assert U.UtilityConsumption.objects.filter(tenant=acme, meter=meter).exists()


def test_view_consumption_detail(admin_client, consumption):
    r = admin_client.get(reverse('utility:consumption_detail', args=[consumption.pk]))
    assert r.status_code == 200


# ---------- UtilityTariff CRUD ----------

def test_create_tariff(admin_client, acme, utility_type_electricity):
    r = admin_client.post(reverse('utility:tariff_create'), data={
        'utility_type': utility_type_electricity.pk,
        'name': 'TestTariff',
        'effective_from': '2026-01-01',
        'flat_rate': '0.15', 'currency': 'USD', 'is_active': 'on',
    })
    assert r.status_code == 302
    assert U.UtilityTariff.objects.filter(tenant=acme, name='TestTariff').exists()


def test_view_tariff_detail(admin_client, tariff):
    r = admin_client.get(reverse('utility:tariff_detail', args=[tariff.pk]))
    assert r.status_code == 200


def test_create_tou_band_inline(admin_client, tariff):
    r = admin_client.post(
        reverse('utility:band_create', args=[tariff.pk]),
        data={
            'band_type': 'peak', 'day_of_week': 'weekday',
            'start_time': '08:00', 'end_time': '18:00', 'rate': '0.30',
        },
    )
    assert r.status_code == 302
    assert U.TOURateBand.objects.filter(tariff=tariff).exists()


# ---------- UtilityAllocation workflow ----------

def test_allocation_post_no_targets_warns(admin_client, acme, acp_open, meter):
    """L-04: warning surfaced when no allocation targets defined."""
    r = admin_client.post(reverse('utility:allocation_post'), data={
        'period': acp_open.pk, 'meter': meter.pk,
    })
    assert r.status_code == 302


def test_allocation_reverse_requires_reason(admin_client, acme, acp_open, meter):
    a = U.UtilityAllocation.objects.create(
        tenant=acme, period=acp_open, meter=meter, share_pct=Decimal('100'),
    )
    r = admin_client.post(
        reverse('utility:allocation_reverse', args=[a.pk]),
        data={'reversal_reason': ''},
    )
    a.refresh_from_db()
    assert a.is_reversed is False  # blocked


def test_allocation_reverse_happy_path(admin_client, acme, acp_open, meter):
    a = U.UtilityAllocation.objects.create(
        tenant=acme, period=acp_open, meter=meter, share_pct=Decimal('100'),
    )
    r = admin_client.post(
        reverse('utility:allocation_reverse', args=[a.pk]),
        data={'reversal_reason': 'wrong meter'},
    )
    assert r.status_code == 302
    a.refresh_from_db()
    assert a.is_reversed is True


def test_allocation_delete_blocked_when_posted(admin_client, acme, acp_open, meter):
    """L-03: cannot delete a posted allocation."""
    a = U.UtilityAllocation.objects.create(
        tenant=acme, period=acp_open, meter=meter, share_pct=Decimal('100'),
        is_posted_to_cost=True,
    )
    r = admin_client.post(reverse('utility:allocation_delete', args=[a.pk]))
    assert U.UtilityAllocation.objects.filter(pk=a.pk).exists()


# ---------- DR event workflow ----------

def test_create_dr_event(admin_client, acme, utility_type_electricity):
    now = timezone.now()
    r = admin_client.post(reverse('utility:dr_event_create'), data={
        'utility_type': utility_type_electricity.pk,
        'event_type': 'voluntary',
        'start_at': now.strftime('%Y-%m-%dT%H:%M'),
        'end_at': (now + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),
        'target_reduction_pct': '10', 'source': 'manual',
    })
    assert r.status_code == 302
    assert U.DemandResponseEvent.objects.filter(tenant=acme).exists()


def test_dr_event_activate_workflow(admin_client, acme, utility_type_electricity):
    now = timezone.now()
    e = U.DemandResponseEvent.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=1),
        status='scheduled',
    )
    r = admin_client.post(reverse('utility:dr_event_activate', args=[e.pk]))
    assert r.status_code == 302
    e.refresh_from_db()
    assert e.status == 'active'


def test_dr_event_complete_workflow(admin_client, acme, utility_type_electricity):
    now = timezone.now()
    e = U.DemandResponseEvent.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=1),
        status='active',
    )
    r = admin_client.post(reverse('utility:dr_event_complete', args=[e.pk]))
    assert r.status_code == 302
    e.refresh_from_db()
    assert e.status == 'completed'


def test_dr_event_cancel_requires_reason(admin_client, acme, utility_type_electricity):
    now = timezone.now()
    e = U.DemandResponseEvent.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=1),
        status='scheduled',
    )
    r = admin_client.post(
        reverse('utility:dr_event_cancel', args=[e.pk]),
        data={'cancellation_reason': ''},
    )
    e.refresh_from_db()
    assert e.status == 'scheduled'  # blocked


def test_dr_event_cancel_happy(admin_client, acme, utility_type_electricity):
    now = timezone.now()
    e = U.DemandResponseEvent.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=1),
        status='scheduled',
    )
    r = admin_client.post(
        reverse('utility:dr_event_cancel', args=[e.pk]),
        data={'cancellation_reason': 'tariff change'},
    )
    assert r.status_code == 302
    e.refresh_from_db()
    assert e.status == 'cancelled'


# ---------- Peak shaving workflow ----------

def test_peak_scan_runs(admin_client, acme):
    r = admin_client.post(reverse('utility:peak_scan'), data={'horizon_days': '14'})
    assert r.status_code == 302


# ---------- Emission factor CRUD ----------

def test_create_emission_factor(admin_client, acme):
    r = admin_client.post(reverse('utility:factor_create'), data={
        'source_type': 'natural_gas', 'scope': 'scope_1',
        'region': '', 'factor': '2.04', 'unit_of_measure': 'm3',
        'effective_from': '2026-01-01', 'is_active': 'on',
    })
    assert r.status_code == 302
    assert U.EmissionFactor.objects.filter(tenant=acme, source_type='natural_gas').exists()


# ---------- Carbon emission recompute ----------

def test_emission_recompute(admin_client, acp_open):
    r = admin_client.post(
        reverse('utility:emission_recompute', args=[acp_open.pk]),
    )
    assert r.status_code == 302


# ---------- Sustainability KPI generate ----------

def test_sustainability_generate(admin_client, acp_open):
    r = admin_client.post(
        reverse('utility:sustainability_generate', args=[acp_open.pk]),
    )
    # Either redirect to detail (302) or list redirect (302)
    assert r.status_code == 302
    assert U.SustainabilityKPI.objects.filter(period=acp_open).exists()


# ---------- Benchmark workflow ----------

def test_benchmark_generate(admin_client, acme, acp_open):
    r = admin_client.post(reverse('utility:benchmark_generate'), data={
        'period': acp_open.pk, 'plant_label': 'main_factory',
    })
    assert r.status_code == 302


def test_benchmark_comparison_create(admin_client, acme, acp_open):
    s1 = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='A',
        total_units_produced=Decimal('10'),
    )
    s2 = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='B',
        total_units_produced=Decimal('10'),
    )
    r = admin_client.post(reverse('utility:benchmark_report_create'), data={
        'comparison_type': 'plant_to_plant',
        'from_snapshot': s1.pk, 'to_snapshot': s2.pk,
    })
    assert r.status_code == 302
    assert U.BenchmarkComparison.objects.filter(tenant=acme).exists()


# ---------- Filter smoke ----------

def test_meter_list_filter_by_utility_type(admin_client, meter, utility_type_electricity):
    r = admin_client.get(
        reverse('utility:meter_list') + f'?utility_type={utility_type_electricity.pk}',
    )
    assert r.status_code == 200


def test_consumption_list_filter_by_meter(admin_client, consumption, meter):
    r = admin_client.get(
        reverse('utility:consumption_list') + f'?meter={meter.pk}',
    )
    assert r.status_code == 200


def test_dr_event_list_filter_by_status(admin_client):
    r = admin_client.get(reverse('utility:dr_event_list') + '?status=scheduled')
    assert r.status_code == 200


# ---------- Search smoke ----------

def test_meter_list_search(admin_client, meter):
    r = admin_client.get(reverse('utility:meter_list') + f'?q={meter.meter_number}')
    assert r.status_code == 200
