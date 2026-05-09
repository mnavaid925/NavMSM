"""Pure-function service coverage for Module 14."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.utility import models as U
from apps.utility.services import (
    allocation as alloc_svc,
    benchmark as bench_svc,
    carbon as carbon_svc,
    meters as meter_svc,
    peak as peak_svc,
)


pytestmark = pytest.mark.django_db


# ---------- Meter service ----------

def test_post_consumption_creates_row(acme, meter):
    now = timezone.now()
    c = meter_svc.post_consumption(
        meter, period_start=now - timedelta(hours=1), period_end=now,
        start_reading=Decimal('0'), end_reading=Decimal('100'),
        unit_cost=Decimal('0.10'), source='manual',
    )
    assert c.entry_number == 'UC-00001'
    assert c.consumption == Decimal('100.0000')
    assert c.total_cost == Decimal('10.00')


def test_post_consumption_idempotent_on_source_meter_reading(acme, meter):
    """Re-running post_consumption with same source_meter_reading returns existing row."""
    from apps.eam.models import Asset, AssetCategory, AssetMeterReading
    cat = AssetCategory.objects.create(tenant=acme, name='Test')
    asset = Asset.objects.create(tenant=acme, category=cat, tag='T1', name='Test')
    reading = AssetMeterReading.objects.create(
        tenant=acme, asset=asset, meter_type='hours',
        reading_value=Decimal('10'),
    )
    now = timezone.now()
    c1 = meter_svc.post_consumption(
        meter, period_start=now - timedelta(hours=1), period_end=now,
        start_reading=Decimal('0'), end_reading=Decimal('10'),
        source_meter_reading=reading,
    )
    c2 = meter_svc.post_consumption(
        meter, period_start=now - timedelta(hours=1), period_end=now,
        start_reading=Decimal('0'), end_reading=Decimal('20'),
        source_meter_reading=reading,
    )
    assert c1.pk == c2.pk


def test_post_consumption_resolves_unit_cost_from_tariff(acme, meter, tariff):
    """When unit_cost is None, the service snapshots the active tariff's flat_rate."""
    now = timezone.now()
    c = meter_svc.post_consumption(
        meter, period_start=now - timedelta(hours=1), period_end=now,
        start_reading=Decimal('0'), end_reading=Decimal('100'),
        unit_cost=None, source='manual',
    )
    assert c.unit_cost == tariff.flat_rate


# ---------- Allocation service ----------

def test_compute_allocation_pure_split(acme, acp_open, meter, consumption):
    from apps.labor.models import CostCenter
    cc1 = CostCenter.objects.create(tenant=acme, code='CC1', name='CC1')
    cc2 = CostCenter.objects.create(tenant=acme, code='CC2', name='CC2')
    targets = [
        {'cost_center': cc1, 'product': None, 'production_order': None, 'share_pct': Decimal('60')},
        {'cost_center': cc2, 'product': None, 'production_order': None, 'share_pct': Decimal('40')},
    ]
    rows = alloc_svc.compute_allocation(acp_open, meter, targets)
    assert len(rows) == 2
    # Total consumption is 50 (start=100, end=150). 60/40 split -> 30 + 20
    assert rows[0]['allocated_consumption'] + rows[1]['allocated_consumption'] == Decimal('50.0000')


def test_post_allocation_writes_cost_driver_actual(acme, acp_open, meter, consumption):
    from apps.cost.models import DriverActuals
    from apps.labor.models import CostCenter
    cc = CostCenter.objects.create(tenant=acme, code='CC1', name='CC1')
    targets = [{
        'cost_center': cc, 'product': None, 'production_order': None,
        'share_pct': Decimal('100'),
    }]
    result = alloc_svc.post_allocation(acp_open, meter, targets)
    assert result['created'] == 1
    da = DriverActuals.all_objects.filter(
        tenant=acme, period=acp_open, cost_center=cc,
    )
    assert da.count() == 1


def test_post_allocation_idempotent_clears_prior(acme, acp_open, meter, consumption):
    from apps.labor.models import CostCenter
    cc = CostCenter.objects.create(tenant=acme, code='CC1', name='CC1')
    targets = [{
        'cost_center': cc, 'product': None, 'production_order': None,
        'share_pct': Decimal('100'),
    }]
    alloc_svc.post_allocation(acp_open, meter, targets)
    result = alloc_svc.post_allocation(acp_open, meter, targets)
    assert result['cleared_prior'] == 1
    assert U.UtilityAllocation.all_objects.filter(
        tenant=acme, period=acp_open, meter=meter, is_reversed=False,
    ).count() == 1


def test_reverse_allocation_removes_driver_actual(acme, acp_open, meter, consumption):
    from apps.cost.models import DriverActuals
    from apps.labor.models import CostCenter
    cc = CostCenter.objects.create(tenant=acme, code='CC1', name='CC1')
    targets = [{
        'cost_center': cc, 'product': None, 'production_order': None,
        'share_pct': Decimal('100'),
    }]
    alloc_svc.post_allocation(acp_open, meter, targets)
    a = U.UtilityAllocation.all_objects.filter(tenant=acme).first()
    alloc_svc.reverse_allocation(a, reason='Test reason')
    assert DriverActuals.all_objects.filter(tenant=acme, period=acp_open).count() == 0
    a.refresh_from_db()
    assert a.is_reversed is True


def test_reverse_allocation_already_reversed_is_idempotent(acme, acp_open, meter, consumption):
    from apps.labor.models import CostCenter
    cc = CostCenter.objects.create(tenant=acme, code='CC1', name='CC1')
    targets = [{
        'cost_center': cc, 'product': None, 'production_order': None,
        'share_pct': Decimal('100'),
    }]
    alloc_svc.post_allocation(acp_open, meter, targets)
    a = U.UtilityAllocation.all_objects.filter(tenant=acme).first()
    alloc_svc.reverse_allocation(a, reason='First')
    a.refresh_from_db()
    result = alloc_svc.reverse_allocation(a, reason='Second')
    assert result.is_reversed is True


# ---------- Peak service ----------

def test_scan_for_peak_overlap_no_ops_returns_empty(acme):
    """No scheduled operations -> no suggestions emitted."""
    result = peak_svc.scan_for_peak_overlap(acme, horizon_days=14)
    assert result == {'created': 0, 'horizon_days': 14}


def test_scan_for_peak_overlap_idempotent(acme):
    """Re-running scan with same data emits zero new rows."""
    peak_svc.scan_for_peak_overlap(acme, horizon_days=14)
    result = peak_svc.scan_for_peak_overlap(acme, horizon_days=14)
    assert result['created'] == 0


def test_compute_estimated_savings_no_band_fallback():
    """When current_band is None, returns the fallback heuristic."""
    now = timezone.now()

    class StubOp:
        planned_start = now
        planned_end = now + timedelta(hours=2)

    savings = peak_svc.compute_estimated_savings(StubOp())
    # 2 hr * 50 kWh/hr * 0.06 = 6.00
    assert savings == Decimal('6.00')


def test_compute_estimated_savings_with_bands(acme, tariff):
    """Rate-diff based saving when current/target bands provided."""
    from datetime import time as dtime
    peak = U.TOURateBand.objects.create(
        tariff=tariff, tenant=acme, band_type='peak',
        day_of_week='all', start_time=dtime(8, 0), end_time=dtime(18, 0),
        rate=Decimal('0.30'),
    )
    off = U.TOURateBand.objects.create(
        tariff=tariff, tenant=acme, band_type='off_peak',
        day_of_week='all', start_time=dtime(22, 0), end_time=dtime(23, 0),
        rate=Decimal('0.10'),
    )
    now = timezone.now()

    class StubOp:
        planned_start = now
        planned_end = now + timedelta(hours=1)

    savings = peak_svc.compute_estimated_savings(
        StubOp(), current_band=peak, target_band=off,
    )
    # 1 hr * 50 kWh/hr * (0.30 - 0.10) = 10.00
    assert savings == Decimal('10.00')


def test_acknowledge_only_from_new(acme, utility_type_electricity):
    """acknowledge() is a no-op for already-acknowledged suggestions."""
    from apps.plm.models import Product, ProductCategory
    from apps.pps.models import (
        ProductionOrder, WorkCenter, ScheduledOperation,
    )
    cat = ProductCategory.objects.create(tenant=acme, code='C', name='C')
    p = Product.objects.create(
        tenant=acme, sku='S', name='X', category=cat,
        product_type='finished_good', unit_of_measure='ea',
    )
    wc = WorkCenter.objects.create(
        tenant=acme, code='WC', name='WC', work_center_type='machine',
    )
    po = ProductionOrder.objects.create(
        tenant=acme, product=p, order_number='PO',
        quantity=Decimal('1'), status='released',
    )
    now = timezone.now()
    op = ScheduledOperation.objects.create(
        tenant=acme, production_order=po, work_center=wc,
        sequence=10, planned_start=now, planned_end=now + timedelta(hours=1),
    )
    sug = U.PeakShavingSuggestion.objects.create(
        tenant=acme, production_order=po, scheduled_operation=op,
        original_start=now, original_end=now + timedelta(hours=1),
        status='dismissed',
    )
    result = peak_svc.acknowledge(sug)
    # Status unchanged because it's not 'new'
    assert result.status == 'dismissed'


# ---------- Carbon service ----------

def test_emit_for_consumption_writes_carbon_row(acme, acp_open, meter, emission_factor_grid):
    now = timezone.now()
    c = U.UtilityConsumption.objects.create(
        tenant=acme, meter=meter,
        period_start=now - timedelta(hours=1), period_end=now,
        start_reading=Decimal('0'), end_reading=Decimal('100'),
        unit_cost=Decimal('0.10'),
    )
    # Signal already auto-emitted; explicit re-call is idempotent
    result = carbon_svc.emit_for_consumption(c)
    assert result is not None
    assert U.CarbonEmission.all_objects.filter(source_consumption=c).count() == 1


def test_emit_returns_none_without_factor(acme, acp_open, meter):
    """Silently skip when no active EmissionFactor matches."""
    now = timezone.now()
    c = U.UtilityConsumption.objects.create(
        tenant=acme, meter=meter,
        period_start=now - timedelta(hours=1), period_end=now,
        start_reading=Decimal('0'), end_reading=Decimal('100'),
    )
    # No emission factor exists -> service returns None
    result = carbon_svc.emit_for_consumption(c)
    assert result is None
    assert U.CarbonEmission.all_objects.filter(source_consumption=c).count() == 0


def test_recompute_emissions_clears_and_re_emits(acme, acp_open, meter, emission_factor_grid):
    """recompute_emissions wipes prior carbon rows then re-emits."""
    now = timezone.now()
    # Anchor consumption inside the period window
    period_dt = timezone.make_aware(
        timezone.datetime(
            acp_open.start_date.year,
            acp_open.start_date.month,
            acp_open.start_date.day, 9, 0,
        )
    )
    c = U.UtilityConsumption.objects.create(
        tenant=acme, meter=meter,
        period_start=period_dt,
        period_end=period_dt + timedelta(hours=1),
        start_reading=Decimal('0'), end_reading=Decimal('100'),
        unit_cost=Decimal('0.10'),
    )
    result = carbon_svc.recompute_emissions(acp_open)
    assert result['emitted'] >= 1
    # Should still have exactly one carbon row for that consumption
    assert U.CarbonEmission.all_objects.filter(source_consumption=c).count() == 1


def test_generate_sustainability_kpi_creates_or_updates(acme, acp_open):
    kpi = carbon_svc.generate_sustainability_kpi(acp_open)
    assert kpi.tenant == acme
    assert kpi.period == acp_open
    # Re-running overwrites
    kpi2 = carbon_svc.generate_sustainability_kpi(acp_open)
    assert kpi.pk == kpi2.pk


# ---------- Benchmark service ----------

def test_compare_returns_pct_deltas(acme, acp_open):
    s1 = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='plant_a',
        total_kwh=Decimal('100'), total_units_produced=Decimal('10'),
    )
    s2 = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='plant_b',
        total_kwh=Decimal('80'), total_units_produced=Decimal('10'),
    )
    # s1: 10 kwh/unit; s2: 8 kwh/unit -> -20%
    deltas = bench_svc.compare(s1, s2)
    assert deltas['kwh_delta_pct'] == Decimal('-20.00')


def test_compare_handles_zero_baseline(acme, acp_open):
    s1 = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='plant_a',
        total_kwh=Decimal('0'), total_units_produced=Decimal('0'),
    )
    s2 = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='plant_b',
        total_kwh=Decimal('80'), total_units_produced=Decimal('10'),
    )
    deltas = bench_svc.compare(s1, s2)
    assert deltas['kwh_delta_pct'] == Decimal('0')


def test_generate_snapshot_is_idempotent(acme, acp_open):
    s1 = bench_svc.generate_snapshot(acp_open, plant_label='factory_x')
    s2 = bench_svc.generate_snapshot(acp_open, plant_label='factory_x')
    assert s1.pk == s2.pk


def test_create_comparison_persists_winner(acme, acp_open):
    s1 = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='A',
        total_kwh=Decimal('100'), total_units_produced=Decimal('10'),
    )
    s2 = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='B',
        total_kwh=Decimal('60'), total_units_produced=Decimal('10'),
    )
    rep = bench_svc.create_comparison(
        comparison_type='plant_to_plant',
        from_snapshot=s1, to_snapshot=s2, tenant=acme,
    )
    # B has lower kwh/unit -> B wins
    assert 'B' in rep.winner
    assert rep.kwh_delta_pct == Decimal('-40.00')
