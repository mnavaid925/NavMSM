"""Form validation: L-01 unique_together, L-02 decimal bounds, L-14 per-workflow required."""
from datetime import date
from decimal import Decimal

import pytest

from apps.cost import forms, models as C


pytestmark = pytest.mark.django_db


# ---------- L-01 unique_together with tenant excluded ----------

def test_cost_driver_form_blocks_duplicate_code(acme, driver):
    form = forms.CostDriverForm(
        tenant=acme,
        data={'name': 'Dup', 'code': driver.code, 'unit_of_measure': 'h', 'is_active': True},
    )
    assert not form.is_valid()
    assert 'code' in form.errors


def test_cost_driver_form_allows_unique_code(acme, driver):
    form = forms.CostDriverForm(
        tenant=acme,
        data={'name': 'New', 'code': 'NEW', 'unit_of_measure': 'h', 'is_active': True},
    )
    assert form.is_valid()


def test_overhead_pool_form_blocks_duplicate(acme, pool, driver):
    form = forms.OverheadPoolForm(
        tenant=acme,
        data={
            'name': 'Dup', 'code': pool.code, 'pool_type': 'fixed',
            'default_driver': driver.pk, 'allocation_method': 'abc',
            'is_active': True,
        },
    )
    assert not form.is_valid()


def test_accounting_period_form_blocks_duplicate_dates(acme, acp_open):
    form = forms.AccountingPeriodForm(
        tenant=acme,
        data={
            'name': 'Dup', 'period_type': 'monthly',
            'start_date': acp_open.start_date.isoformat(),
            'end_date': acp_open.end_date.isoformat(),
        },
    )
    assert not form.is_valid()


def test_accounting_period_form_blocks_invalid_range(acme):
    form = forms.AccountingPeriodForm(
        tenant=acme,
        data={
            'name': 'Bad', 'period_type': 'monthly',
            'start_date': '2026-02-01', 'end_date': '2026-01-15',
        },
    )
    assert not form.is_valid()


# ---------- L-14 per-workflow required ----------

def test_approve_form_requires_notes():
    f = forms.StandardCostVersionApproveForm(data={'notes': ''})
    assert not f.is_valid()
    f = forms.StandardCostVersionApproveForm(data={'notes': '   '})
    assert not f.is_valid()
    f = forms.StandardCostVersionApproveForm(data={'notes': 'Looks good'})
    assert f.is_valid()


def test_overhead_reverse_form_requires_reason():
    f = forms.OverheadReverseForm(data={'reversal_reason': ''})
    assert not f.is_valid()
    f = forms.OverheadReverseForm(data={'reversal_reason': 'Oops'})
    assert f.is_valid()


def test_period_lock_form_requires_confirm():
    f = forms.AccountingPeriodLockForm(data={})
    assert not f.is_valid()
    f = forms.AccountingPeriodLockForm(data={'confirm': True})
    assert f.is_valid()


# ---------- DriverActuals XOR ----------

def test_driver_actuals_form_requires_one_target(acme, acp_open, driver):
    f = forms.DriverActualsForm(
        tenant=acme,
        data={
            'driver': driver.pk, 'period': acp_open.pk,
            'quantity': '10',
        },
    )
    assert not f.is_valid()
    assert any('Cost Center' in str(e) or 'Production' in str(e) for e in f.errors.get('__all__', []))


def test_driver_actuals_form_rejects_both(acme, acp_open, driver, production_order):
    from apps.labor.models import CostCenter
    cc = CostCenter.objects.create(tenant=acme, code='X', name='X')
    f = forms.DriverActualsForm(
        tenant=acme,
        data={
            'driver': driver.pk, 'period': acp_open.pk,
            'cost_center': cc.pk, 'production_order': production_order.pk,
            'quantity': '10',
        },
    )
    assert not f.is_valid()


def test_driver_actuals_form_accepts_just_cc(acme, acp_open, driver):
    from apps.labor.models import CostCenter
    cc = CostCenter.objects.create(tenant=acme, code='X', name='X')
    f = forms.DriverActualsForm(
        tenant=acme,
        data={
            'driver': driver.pk, 'period': acp_open.pk,
            'cost_center': cc.pk, 'quantity': '10',
        },
    )
    assert f.is_valid()


# ---------- StandardCost duplicate guard ----------

def test_standard_cost_form_blocks_duplicate_product_in_version(acme, cost_version, product, standard_cost):
    f = forms.StandardCostForm(
        tenant=acme, version=cost_version,
        data={
            'product': product.pk, 'material_cost': '1', 'labor_cost': '0',
            'overhead_cost': '0', 'tooling_cost': '0', 'subassembly_cost': '0',
            'source': 'manual', 'currency': 'USD',
        },
    )
    assert not f.is_valid()


# ---------- L-02 decimal bounds via model validators (form-level) ----------

def test_overhead_rate_form_rejects_zero_qty(acme, pool, acp_open, driver):
    f = forms.OverheadRateForm(
        tenant=acme,
        data={
            'pool': pool.pk, 'period': acp_open.pk, 'driver': driver.pk,
            'budgeted_amount': '100', 'budgeted_driver_qty': '0',
            'is_active': True,
        },
    )
    # MinValueValidator(0.0001) on the model -> form should reject 0
    assert not f.is_valid()


def test_standard_cost_version_form_clean_dates(acme):
    f = forms.StandardCostVersionForm(
        tenant=acme,
        data={'name': 'V', 'effective_from': '2026-02-01', 'effective_to': '2026-01-15'},
    )
    assert not f.is_valid()
    assert 'effective_to' in f.errors
