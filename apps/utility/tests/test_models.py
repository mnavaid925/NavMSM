"""Model invariants + auto-numbering + denorm computations for Module 14."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.utility import models as U


pytestmark = pytest.mark.django_db


# ---------- Auto-numbering ----------

def test_meter_auto_number(acme, utility_type_electricity):
    m = U.UtilityMeter.objects.create(
        tenant=acme, utility_type=utility_type_electricity, name='M1',
    )
    assert m.meter_number == 'MTR-00001'
    m2 = U.UtilityMeter.objects.create(
        tenant=acme, utility_type=utility_type_electricity, name='M2',
    )
    assert m2.meter_number == 'MTR-00002'


def test_consumption_auto_number(acme, meter):
    now = timezone.now()
    c = U.UtilityConsumption.objects.create(
        tenant=acme, meter=meter,
        period_start=now - timedelta(hours=1), period_end=now,
        start_reading=Decimal('100'), end_reading=Decimal('110'),
    )
    assert c.entry_number == 'UC-00001'


def test_tariff_auto_number(acme, utility_type_electricity):
    t = U.UtilityTariff.objects.create(
        tenant=acme, utility_type=utility_type_electricity, name='T1',
        effective_from=date(2026, 1, 1), flat_rate=Decimal('0.10'),
    )
    assert t.tariff_number == 'TRF-00001'


def test_allocation_auto_number(acme, acp_open, meter):
    a = U.UtilityAllocation.objects.create(
        tenant=acme, period=acp_open, meter=meter,
        share_pct=Decimal('100'),
    )
    assert a.allocation_number == 'UAL-00001'


def test_dr_event_auto_number(acme, utility_type_electricity):
    now = timezone.now()
    e = U.DemandResponseEvent.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=2),
    )
    assert e.event_number == 'DRE-00001'


def test_pss_auto_number_via_create(acme, utility_type_electricity):
    """PSS requires production_order + scheduled_operation; build minimal chain inline."""
    from apps.plm.models import Product, ProductCategory
    from apps.pps.models import (
        ProductionOrder, WorkCenter, ScheduledOperation,
    )
    cat = ProductCategory.objects.create(tenant=acme, code='C1', name='C1')
    p = Product.objects.create(
        tenant=acme, sku='SKU1', name='X', category=cat,
        product_type='finished_good', unit_of_measure='ea',
    )
    wc = WorkCenter.objects.create(
        tenant=acme, code='WC1', name='WC1', work_center_type='machine',
    )
    po = ProductionOrder.objects.create(
        tenant=acme, product=p, order_number='PO1',
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
    )
    assert sug.suggestion_number == 'PSS-00001'


def test_carbon_emission_auto_number(acme, acp_open, emission_factor_grid):
    e = U.CarbonEmission.objects.create(
        tenant=acme, period=acp_open, scope='scope_2',
        source_type='electricity_grid', source_quantity=Decimal('100'),
        factor=emission_factor_grid,
    )
    assert e.entry_number == 'CE-00001'


def test_benchmark_comparison_auto_number(acme, acp_open):
    s1 = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='A',
        total_units_produced=Decimal('10'),
    )
    s2 = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='B',
        total_units_produced=Decimal('10'),
    )
    r = U.BenchmarkComparison.objects.create(
        tenant=acme, comparison_type='plant_to_plant',
        from_snapshot=s1, to_snapshot=s2,
    )
    assert r.report_number == 'BCR-00001'


# ---------- Unique together ----------

def test_utility_type_unique_code(acme, utility_type_electricity):
    with pytest.raises(Exception):
        U.UtilityType.objects.create(
            tenant=acme, code='electricity', name='Dup',
        )


def test_meter_unique_type_and_name(acme, utility_type_electricity, meter):
    with pytest.raises(Exception):
        U.UtilityMeter.objects.create(
            tenant=acme, utility_type=utility_type_electricity, name=meter.name,
        )


def test_emission_factor_unique_per_source_scope_region_date(acme, emission_factor_grid):
    with pytest.raises(Exception):
        U.EmissionFactor.objects.create(
            tenant=acme, source_type='electricity_grid', scope='scope_2',
            region='', factor=Decimal('0.5'), unit_of_measure='kwh',
            effective_from=emission_factor_grid.effective_from,
        )


def test_sustainability_kpi_unique_per_period(acme, acp_open):
    U.SustainabilityKPI.objects.create(tenant=acme, period=acp_open)
    with pytest.raises(Exception):
        U.SustainabilityKPI.objects.create(tenant=acme, period=acp_open)


def test_consumption_source_meter_reading_unique(acme, meter):
    """Partial unique constraint blocks duplicate auto-feed signals."""
    from django.db import IntegrityError, transaction
    from apps.eam.models import Asset, AssetCategory, AssetMeterReading
    cat = AssetCategory.objects.create(tenant=acme, name='AC1')
    asset = Asset.objects.create(tenant=acme, category=cat, tag='T1', name='Test')
    reading = AssetMeterReading.objects.create(
        tenant=acme, asset=asset, meter_type='hours',
        reading_value=Decimal('10'),
    )
    now = timezone.now()
    U.UtilityConsumption.objects.create(
        tenant=acme, meter=meter,
        period_start=now - timedelta(hours=1), period_end=now,
        start_reading=Decimal('0'), end_reading=Decimal('1'),
        source_meter_reading=reading,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            U.UtilityConsumption.objects.create(
                tenant=acme, meter=meter,
                period_start=now - timedelta(hours=1), period_end=now,
                start_reading=Decimal('0'), end_reading=Decimal('1'),
                source_meter_reading=reading,
            )


# ---------- L-02 decimal validators ----------

def test_meter_multiplier_min_value(acme, utility_type_electricity):
    m = U.UtilityMeter(
        tenant=acme, utility_type=utility_type_electricity, name='Bad',
        multiplier=Decimal('-1'),
    )
    with pytest.raises(ValidationError):
        m.full_clean()


def test_consumption_unit_cost_min(acme, meter):
    now = timezone.now()
    c = U.UtilityConsumption(
        tenant=acme, meter=meter,
        period_start=now - timedelta(hours=1), period_end=now,
        start_reading=Decimal('0'), end_reading=Decimal('10'),
        unit_cost=Decimal('-1'),
    )
    with pytest.raises(ValidationError):
        c.full_clean()


def test_allocation_share_pct_max(acme, acp_open, meter):
    a = U.UtilityAllocation(
        tenant=acme, period=acp_open, meter=meter,
        share_pct=Decimal('150'),
    )
    with pytest.raises(ValidationError):
        a.full_clean()


def test_emission_factor_min(acme):
    f = U.EmissionFactor(
        tenant=acme, source_type='electricity_grid', scope='scope_2',
        factor=Decimal('-0.1'), unit_of_measure='kwh',
        effective_from=date(2026, 1, 1),
    )
    with pytest.raises(ValidationError):
        f.full_clean()


def test_dr_event_target_reduction_pct_max(acme, utility_type_electricity):
    now = timezone.now()
    e = U.DemandResponseEvent(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=1),
        target_reduction_pct=Decimal('200'),
    )
    with pytest.raises(ValidationError):
        e.full_clean()


# ---------- Denorm computations ----------

def test_consumption_denorm_consumption_and_total(acme, meter):
    now = timezone.now()
    c = U.UtilityConsumption.objects.create(
        tenant=acme, meter=meter,
        period_start=now - timedelta(hours=1), period_end=now,
        start_reading=Decimal('100'), end_reading=Decimal('150'),
        unit_cost=Decimal('0.20'),
    )
    # delta=50 * mult(1.0) = 50
    assert c.consumption == Decimal('50.0000')
    # total_cost = 50 * 0.20 = 10.00
    assert c.total_cost == Decimal('10.00')


def test_consumption_with_meter_multiplier(acme, utility_type_electricity):
    m = U.UtilityMeter.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        name='HV Meter', multiplier=Decimal('10'),
    )
    now = timezone.now()
    c = U.UtilityConsumption.objects.create(
        tenant=acme, meter=m,
        period_start=now - timedelta(hours=1), period_end=now,
        start_reading=Decimal('0'), end_reading=Decimal('5'),
        unit_cost=Decimal('0.10'),
    )
    # delta=5 * mult=10 = 50
    assert c.consumption == Decimal('50.0000')
    assert c.total_cost == Decimal('5.00')


def test_consumption_negative_delta_clamped(acme, meter):
    now = timezone.now()
    c = U.UtilityConsumption.objects.create(
        tenant=acme, meter=meter,
        period_start=now - timedelta(hours=1), period_end=now,
        start_reading=Decimal('100'), end_reading=Decimal('50'),
        unit_cost=Decimal('0.50'),
    )
    assert c.consumption == Decimal('0.0000')
    assert c.total_cost == Decimal('0.00')


def test_carbon_emission_co2e_recomputes(acme, acp_open, emission_factor_grid):
    e = U.CarbonEmission.objects.create(
        tenant=acme, period=acp_open, scope='scope_2',
        source_type='electricity_grid', source_quantity=Decimal('100'),
        factor=emission_factor_grid,
    )
    # 100 * 0.42 = 42.0000
    assert e.co2e_kg == Decimal('42.0000')


def test_sustainability_kpi_total_co2e_sums(acme, acp_open):
    k = U.SustainabilityKPI.objects.create(
        tenant=acme, period=acp_open,
        total_scope_1_kg=Decimal('100'),
        total_scope_2_kg=Decimal('200'),
        total_scope_3_kg=Decimal('50'),
        total_kwh=Decimal('1000'),
        total_units_produced=Decimal('10'),
    )
    assert k.total_co2e_kg == Decimal('350')
    assert k.kwh_per_unit_produced == Decimal('100.0000')
    assert k.co2e_per_unit_produced == Decimal('35.0000')


def test_sustainability_kpi_zero_units(acme, acp_open):
    k = U.SustainabilityKPI.objects.create(
        tenant=acme, period=acp_open,
        total_scope_2_kg=Decimal('100'),
        total_kwh=Decimal('500'),
        total_units_produced=Decimal('0'),
    )
    assert k.kwh_per_unit_produced == Decimal('0')
    assert k.co2e_per_unit_produced == Decimal('0')


def test_benchmark_snapshot_kwh_per_unit(acme, acp_open):
    s = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='main',
        total_kwh=Decimal('1000'), total_water_m3=Decimal('50'),
        total_co2e_kg=Decimal('420'), total_cost=Decimal('120'),
        total_units_produced=Decimal('10'),
    )
    assert s.kwh_per_unit == Decimal('100.0000')
    assert s.water_per_unit == Decimal('5.0000')
    assert s.co2e_per_unit == Decimal('42.0000')
    assert s.cost_per_unit == Decimal('12.0000')


def test_benchmark_snapshot_zero_units(acme, acp_open):
    s = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='empty',
        total_kwh=Decimal('1000'), total_units_produced=Decimal('0'),
    )
    assert s.kwh_per_unit == Decimal('0')
    assert s.cost_per_unit == Decimal('0')


def test_benchmark_snapshot_industry_avg_allows_null_tenant(acp_open):
    """tenant=None allowed for the anonymized industry-average row."""
    s = U.BenchmarkSnapshot.objects.create(
        tenant=None, period=acp_open, plant_label='industry_avg',
        total_kwh=Decimal('1500'), total_units_produced=Decimal('15'),
    )
    assert s.tenant_id is None
    assert s.kwh_per_unit == Decimal('100.0000')


# ---------- Workflow helpers ----------

def test_dr_event_workflow_helpers(acme, utility_type_electricity):
    now = timezone.now()
    e = U.DemandResponseEvent.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=1),
        status='scheduled',
    )
    assert e.is_activatable() and not e.is_completable() and e.is_cancellable()
    e.status = 'active'
    assert e.is_completable() and e.is_cancellable() and not e.is_activatable()
    e.status = 'completed'
    assert not (e.is_activatable() or e.is_completable() or e.is_cancellable())


def test_pss_workflow_helpers(acme, utility_type_electricity):
    """is_acknowledgable / is_dismissable status gates."""
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
        status='new',
    )
    assert sug.is_acknowledgable() and sug.is_dismissable()
    sug.status = 'acknowledged'
    assert not sug.is_acknowledgable() and sug.is_dismissable()
    sug.status = 'dismissed'
    assert not (sug.is_acknowledgable() or sug.is_dismissable())


# ---------- str() smoke ----------

def test_str_methods(acme, utility_type_electricity, meter, tariff, emission_factor_grid):
    assert utility_type_electricity.code in str(utility_type_electricity)
    assert meter.meter_number in str(meter)
    assert tariff.tariff_number in str(tariff)
    assert 'kgCO2e' in str(emission_factor_grid)
