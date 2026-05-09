"""Form validation: L-01 unique_together, L-02 decimal bounds, L-14 per-workflow required."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.utility import forms, models as U


pytestmark = pytest.mark.django_db


# ---------- L-01 unique_together with tenant excluded ----------

def test_utility_type_form_blocks_duplicate_code(acme, utility_type_electricity):
    f = forms.UtilityTypeForm(
        tenant=acme,
        data={
            'code': 'electricity', 'name': 'Dup',
            'unit_of_measure': 'kwh', 'is_active': True,
        },
    )
    assert not f.is_valid()
    assert 'code' in f.errors


def test_utility_type_form_allows_unique_code(acme, utility_type_electricity):
    f = forms.UtilityTypeForm(
        tenant=acme,
        data={
            'code': 'natural_gas', 'name': 'Gas',
            'unit_of_measure': 'm3', 'is_active': True,
        },
    )
    assert f.is_valid(), f.errors


def test_utility_meter_form_blocks_duplicate_name(acme, utility_type_electricity, meter):
    f = forms.UtilityMeterForm(
        tenant=acme,
        data={
            'utility_type': utility_type_electricity.pk,
            'name': meter.name, 'multiplier': '1.0',
            'is_active': True,
        },
    )
    assert not f.is_valid()
    assert 'name' in f.errors


def test_utility_meter_form_allows_unique_name(acme, utility_type_electricity):
    f = forms.UtilityMeterForm(
        tenant=acme,
        data={
            'utility_type': utility_type_electricity.pk,
            'name': 'Brand New Meter', 'multiplier': '1.0',
            'is_active': True,
        },
    )
    assert f.is_valid(), f.errors


def test_emission_factor_form_blocks_duplicate(acme, emission_factor_grid):
    f = forms.EmissionFactorForm(
        tenant=acme,
        data={
            'source_type': 'electricity_grid', 'scope': 'scope_2',
            'region': '', 'factor': '0.5', 'unit_of_measure': 'kwh',
            'effective_from': emission_factor_grid.effective_from.isoformat(),
            'is_active': True,
        },
    )
    assert not f.is_valid()


# ---------- L-02 decimal bounds (form-level via model validators) ----------

def test_consumption_form_rejects_negative_unit_cost(acme, meter):
    now = timezone.now()
    f = forms.UtilityConsumptionForm(
        tenant=acme,
        data={
            'meter': meter.pk,
            'period_start': (now - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
            'period_end': now.strftime('%Y-%m-%dT%H:%M'),
            'start_reading': '0', 'end_reading': '10',
            'unit_cost': '-1', 'source': 'manual',
        },
    )
    assert not f.is_valid()


def test_consumption_form_rejects_end_before_start(acme, meter):
    now = timezone.now()
    f = forms.UtilityConsumptionForm(
        tenant=acme,
        data={
            'meter': meter.pk,
            'period_start': now.strftime('%Y-%m-%dT%H:%M'),
            'period_end': (now - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
            'start_reading': '0', 'end_reading': '10',
            'unit_cost': '0.10', 'source': 'manual',
        },
    )
    assert not f.is_valid()
    assert 'period_end' in f.errors


def test_consumption_form_rejects_end_reading_lower_than_start(acme, meter):
    now = timezone.now()
    f = forms.UtilityConsumptionForm(
        tenant=acme,
        data={
            'meter': meter.pk,
            'period_start': (now - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
            'period_end': now.strftime('%Y-%m-%dT%H:%M'),
            'start_reading': '100', 'end_reading': '50',
            'unit_cost': '0.10', 'source': 'manual',
        },
    )
    assert not f.is_valid()
    assert 'end_reading' in f.errors


def test_tariff_form_blocks_invalid_date_range(acme, utility_type_electricity):
    f = forms.UtilityTariffForm(
        tenant=acme,
        data={
            'utility_type': utility_type_electricity.pk, 'name': 'T',
            'effective_from': '2026-02-01', 'effective_to': '2026-01-15',
            'flat_rate': '0.10', 'currency': 'USD', 'is_active': True,
        },
    )
    assert not f.is_valid()
    assert 'effective_to' in f.errors


def test_tariff_form_rejects_bad_currency(acme, utility_type_electricity):
    f = forms.UtilityTariffForm(
        tenant=acme,
        data={
            'utility_type': utility_type_electricity.pk, 'name': 'T',
            'effective_from': '2026-01-01',
            'flat_rate': '0.10', 'currency': 'WRONG',
            'is_active': True,
        },
    )
    assert not f.is_valid()
    assert 'currency' in f.errors


def test_tou_band_form_blocks_invalid_time_range():
    f = forms.TOURateBandForm(data={
        'band_type': 'peak', 'day_of_week': 'weekday',
        'start_time': '17:00', 'end_time': '08:00', 'rate': '0.30',
    })
    assert not f.is_valid()
    assert 'end_time' in f.errors


def test_dr_event_form_blocks_invalid_window(acme, utility_type_electricity):
    now = timezone.now()
    f = forms.DemandResponseEventForm(
        tenant=acme,
        data={
            'utility_type': utility_type_electricity.pk,
            'event_type': 'voluntary',
            'start_at': now.strftime('%Y-%m-%dT%H:%M'),
            'end_at': (now - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
            'target_reduction_pct': '10', 'source': 'manual',
        },
    )
    assert not f.is_valid()
    assert 'end_at' in f.errors


# ---------- UtilityAllocationForm ----------

def test_allocation_form_requires_at_least_one_target(acme, acp_open, meter):
    f = forms.UtilityAllocationForm(
        tenant=acme,
        data={
            'period': acp_open.pk, 'meter': meter.pk,
            'allocation_method': 'meter_consumption',
            'share_pct': '100',
        },
    )
    assert not f.is_valid()


def test_allocation_form_rejects_share_over_100(acme, acp_open, meter):
    from apps.labor.models import CostCenter
    cc = CostCenter.objects.create(tenant=acme, code='CC1', name='CC1')
    f = forms.UtilityAllocationForm(
        tenant=acme,
        data={
            'period': acp_open.pk, 'meter': meter.pk,
            'target_cost_center': cc.pk,
            'allocation_method': 'meter_consumption',
            'share_pct': '150',
        },
    )
    assert not f.is_valid()
    assert 'share_pct' in f.errors


def test_allocation_form_rejects_zero_share(acme, acp_open, meter):
    from apps.labor.models import CostCenter
    cc = CostCenter.objects.create(tenant=acme, code='CC2', name='CC2')
    f = forms.UtilityAllocationForm(
        tenant=acme,
        data={
            'period': acp_open.pk, 'meter': meter.pk,
            'target_cost_center': cc.pk,
            'allocation_method': 'meter_consumption',
            'share_pct': '0',
        },
    )
    assert not f.is_valid()
    assert 'share_pct' in f.errors


def test_allocation_form_accepts_just_cc(acme, acp_open, meter):
    from apps.labor.models import CostCenter
    cc = CostCenter.objects.create(tenant=acme, code='CC3', name='CC3')
    f = forms.UtilityAllocationForm(
        tenant=acme,
        data={
            'period': acp_open.pk, 'meter': meter.pk,
            'target_cost_center': cc.pk,
            'allocation_method': 'meter_consumption',
            'share_pct': '50',
        },
    )
    assert f.is_valid(), f.errors


# ---------- L-14 per-workflow required ----------

def test_allocation_reverse_form_requires_reason():
    f = forms.UtilityAllocationReverseForm(data={'reversal_reason': ''})
    assert not f.is_valid()
    f = forms.UtilityAllocationReverseForm(data={'reversal_reason': '   '})
    assert not f.is_valid()
    f = forms.UtilityAllocationReverseForm(data={'reversal_reason': 'Wrong meter'})
    assert f.is_valid()


def test_dr_event_cancel_form_requires_reason():
    f = forms.DemandResponseEventCancelForm(data={'cancellation_reason': ''})
    assert not f.is_valid()
    f = forms.DemandResponseEventCancelForm(data={'cancellation_reason': 'no longer needed'})
    assert f.is_valid()


def test_pss_dismiss_form_requires_reason():
    f = forms.PeakShavingDismissForm(data={'dismiss_reason': ''})
    assert not f.is_valid()
    f = forms.PeakShavingDismissForm(data={'dismiss_reason': 'cannot reschedule'})
    assert f.is_valid()


def test_peak_scan_form_horizon_bounds():
    f = forms.PeakShavingScanForm(data={'horizon_days': 0})
    assert not f.is_valid()
    f = forms.PeakShavingScanForm(data={'horizon_days': 100})
    assert not f.is_valid()
    f = forms.PeakShavingScanForm(data={'horizon_days': 14})
    assert f.is_valid()


# ---------- BenchmarkComparisonForm ----------

def test_benchmark_comparison_form_rejects_self_pair(acme, acp_open):
    s = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='A',
        total_units_produced=Decimal('10'),
    )
    f = forms.BenchmarkComparisonForm(
        tenant=acme,
        data={
            'comparison_type': 'plant_to_plant',
            'from_snapshot': s.pk, 'to_snapshot': s.pk,
        },
    )
    assert not f.is_valid()


def test_benchmark_comparison_form_accepts_distinct_pair(acme, acp_open):
    s1 = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='A',
        total_units_produced=Decimal('10'),
    )
    s2 = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='B',
        total_units_produced=Decimal('10'),
    )
    f = forms.BenchmarkComparisonForm(
        tenant=acme,
        data={
            'comparison_type': 'plant_to_plant',
            'from_snapshot': s1.pk, 'to_snapshot': s2.pk,
        },
    )
    assert f.is_valid(), f.errors
