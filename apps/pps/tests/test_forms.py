"""Form validation tests — D-02, D-03, D-04, D-05 regression coverage."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.pps.forms import (
    DemandForecastForm, MasterProductionScheduleForm,
    OptimizationObjectiveForm, ProductionOrderForm, RoutingForm,
    WorkCenterForm,
)
from apps.pps.models import OptimizationObjective, Routing, WorkCenter


# --- BR / cross-field validation ---

@pytest.mark.django_db
class TestMPSForm:
    def test_horizon_end_before_start_rejected(self):
        form = MasterProductionScheduleForm(data={
            'name': 'X',
            'horizon_start': date.today(),
            'horizon_end': date.today() - timedelta(days=1),
            'time_bucket': 'week',
            'description': '',
        })
        assert not form.is_valid()
        assert 'horizon_end' in form.errors


@pytest.mark.django_db
class TestForecastForm:
    def test_period_end_before_start_rejected(self, acme, product):
        form = DemandForecastForm(tenant=acme, data={
            'product': product.pk,
            'period_start': date.today(),
            'period_end': date.today() - timedelta(days=1),
            'forecast_qty': '10',
            'source': 'manual',
            'confidence_pct': '80',
            'notes': '',
        })
        assert not form.is_valid()
        assert 'period_end' in form.errors


@pytest.mark.django_db
class TestOptimizationObjectiveAllZeroWeights:
    def test_all_zero_weights_rejected(self):
        form = OptimizationObjectiveForm(data={
            'name': 'Zero',
            'description': '',
            'weight_changeovers': '0',
            'weight_idle': '0',
            'weight_lateness': '0',
            'weight_priority': '0',
            'is_default': False,
        })
        assert not form.is_valid()


# --- D-02 / D-03 L-01 regression: form must catch the (tenant, X) duplicate. ---

@pytest.mark.django_db
class TestUniqueTrifectaD02:
    def test_workcenter_form_catches_duplicate_code(self, acme):
        WorkCenter.objects.create(
            tenant=acme, code='DUP', name='A', work_center_type='machine',
            capacity_per_hour=Decimal('1'), efficiency_pct=Decimal('100'),
            cost_per_hour=Decimal('1'),
        )
        form = WorkCenterForm(tenant=acme, data={
            'code': 'DUP', 'name': 'B', 'work_center_type': 'machine',
            'capacity_per_hour': '1', 'efficiency_pct': '100',
            'cost_per_hour': '1', 'description': '', 'is_active': True,
        })
        assert not form.is_valid()
        assert 'code' in form.errors

    def test_workcenter_form_allows_same_code_in_different_tenant(self, acme, globex):
        WorkCenter.objects.create(
            tenant=acme, code='DUP', name='A', work_center_type='machine',
            capacity_per_hour=Decimal('1'), efficiency_pct=Decimal('100'),
            cost_per_hour=Decimal('1'),
        )
        form = WorkCenterForm(tenant=globex, data={
            'code': 'DUP', 'name': 'A', 'work_center_type': 'machine',
            'capacity_per_hour': '1', 'efficiency_pct': '100',
            'cost_per_hour': '1', 'description': '', 'is_active': True,
        })
        assert form.is_valid()

    def test_routing_form_catches_duplicate_product_version(self, acme, product, acme_admin):
        Routing.objects.create(
            tenant=acme, product=product, version='A', routing_number='ROUT-1',
            status='draft', created_by=acme_admin,
        )
        form = RoutingForm(tenant=acme, data={
            'name': 'Second', 'product': product.pk, 'version': 'A',
            'is_default': False, 'description': '',
        })
        assert not form.is_valid()
        assert 'version' in form.errors

    def test_objective_form_catches_duplicate_name(self, acme):
        OptimizationObjective.objects.create(
            tenant=acme, name='Balanced',
            weight_changeovers=Decimal('1'), weight_idle=Decimal('1'),
            weight_lateness=Decimal('1'), weight_priority=Decimal('1'),
        )
        form = OptimizationObjectiveForm(tenant=acme, data={
            'name': 'Balanced', 'description': '',
            'weight_changeovers': '1', 'weight_idle': '1',
            'weight_lateness': '1', 'weight_priority': '1',
            'is_default': False,
        })
        assert not form.is_valid()
        assert 'name' in form.errors


# --- D-04 L-02 regression: form must reject out-of-range numeric input. ---

@pytest.mark.django_db
class TestWorkCenterFormBoundsD04:
    def test_negative_capacity_rejected_at_form(self, acme):
        form = WorkCenterForm(tenant=acme, data={
            'code': 'NEG', 'name': 'A', 'work_center_type': 'machine',
            'capacity_per_hour': '-5', 'efficiency_pct': '100',
            'cost_per_hour': '1', 'description': '', 'is_active': True,
        })
        assert not form.is_valid()
        assert 'capacity_per_hour' in form.errors

    def test_efficiency_above_100_rejected_at_form(self, acme):
        form = WorkCenterForm(tenant=acme, data={
            'code': 'OVER', 'name': 'A', 'work_center_type': 'machine',
            'capacity_per_hour': '1', 'efficiency_pct': '999',
            'cost_per_hour': '1', 'description': '', 'is_active': True,
        })
        assert not form.is_valid()
        assert 'efficiency_pct' in form.errors

    def test_negative_cost_rejected_at_form(self, acme):
        form = WorkCenterForm(tenant=acme, data={
            'code': 'NEGC', 'name': 'A', 'work_center_type': 'machine',
            'capacity_per_hour': '1', 'efficiency_pct': '100',
            'cost_per_hour': '-100', 'description': '', 'is_active': True,
        })
        assert not form.is_valid()
        assert 'cost_per_hour' in form.errors


# --- D-05 regression: order requested_end > requested_start. ---

@pytest.mark.django_db
class TestProductionOrderDateValidationD05:
    def test_requested_end_before_start_rejected(self, acme, product):
        ts = timezone.now()
        form = ProductionOrderForm(tenant=acme, data={
            'product': product.pk,
            'quantity': '5',
            'priority': 'normal',
            'scheduling_method': 'forward',
            'requested_start': ts.strftime('%Y-%m-%dT%H:%M'),
            'requested_end': (ts - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
            'notes': '',
        })
        assert not form.is_valid()
        assert 'requested_end' in form.errors

    def test_requested_end_equal_to_start_rejected(self, acme, product):
        ts = timezone.now()
        form = ProductionOrderForm(tenant=acme, data={
            'product': product.pk,
            'quantity': '5',
            'priority': 'normal',
            'scheduling_method': 'forward',
            'requested_start': ts.strftime('%Y-%m-%dT%H:%M'),
            'requested_end': ts.strftime('%Y-%m-%dT%H:%M'),
            'notes': '',
        })
        assert not form.is_valid()
        assert 'requested_end' in form.errors
