"""Form validation tests."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.inventory import forms, models as inv_models


pytestmark = pytest.mark.django_db


def test_warehouse_form_rejects_duplicate_code(acme, warehouse):
    f = forms.WarehouseForm(
        data={'code': warehouse.code, 'name': 'Dup', 'is_active': True},
        tenant=acme,
    )
    assert not f.is_valid()
    assert 'code' in f.errors


def test_warehouse_form_allows_same_code_different_tenant(acme, globex, warehouse):
    f = forms.WarehouseForm(
        data={'code': warehouse.code, 'name': 'Different tenant', 'is_active': True},
        tenant=globex,
    )
    assert f.is_valid()


def test_zone_form_rejects_duplicate_in_warehouse(acme, warehouse, storage_zone):
    f = forms.WarehouseZoneForm(
        data={
            'warehouse': warehouse.pk, 'code': storage_zone.code,
            'name': 'Dup', 'zone_type': 'storage', 'is_active': True,
        },
        tenant=acme,
    )
    assert not f.is_valid()
    assert 'code' in f.errors


def test_lot_form_rejects_expiry_before_manufactured(acme, fg_product):
    today = timezone.now().date()
    f = forms.LotForm(
        data={
            'product': fg_product.pk, 'lot_number': 'L-bad',
            'manufactured_date': today.isoformat(),
            'expiry_date': (today - timedelta(days=1)).isoformat(),
            'status': 'active',
        },
        tenant=acme,
    )
    assert not f.is_valid()
    assert 'expiry_date' in f.errors


def test_lot_form_rejects_duplicate_lot_per_product(acme, fg_product):
    inv_models.Lot.objects.create(
        tenant=acme, product=fg_product, lot_number='L-1',
    )
    f = forms.LotForm(
        data={'product': fg_product.pk, 'lot_number': 'L-1', 'status': 'active'},
        tenant=acme,
    )
    assert not f.is_valid()
    assert 'lot_number' in f.errors


def test_movement_form_requires_to_bin_for_receipt(acme, fg_product):
    f = forms.StockMovementForm(
        data={
            'movement_type': 'receipt',
            'product': fg_product.pk,
            'qty': '5',
        },
        tenant=acme,
    )
    assert not f.is_valid()
    assert 'to_bin' in f.errors


def test_movement_form_transfer_requires_both(acme, fg_product, bin_a):
    f = forms.StockMovementForm(
        data={
            'movement_type': 'transfer',
            'product': fg_product.pk,
            'qty': '5',
            'from_bin': bin_a.pk,
        },
        tenant=acme,
    )
    assert not f.is_valid()


def test_movement_form_transfer_rejects_same_bin(acme, fg_product, bin_a):
    """Regression for BUG-01 (TC-NEG-03): transfer with from_bin == to_bin must be rejected."""
    f = forms.StockMovementForm(
        data={
            'movement_type': 'transfer',
            'product': fg_product.pk,
            'qty': '5',
            'from_bin': bin_a.pk,
            'to_bin': bin_a.pk,
        },
        tenant=acme,
    )
    assert not f.is_valid()
    errors = str(f.errors)
    assert 'must differ' in errors.lower()


def test_movement_form_adjustment_rejects_both(acme, fg_product, bin_a, bin_b):
    f = forms.StockMovementForm(
        data={
            'movement_type': 'adjustment',
            'product': fg_product.pk,
            'qty': '5',
            'from_bin': bin_a.pk,
            'to_bin': bin_b.pk,
        },
        tenant=acme,
    )
    assert not f.is_valid()


def test_transfer_form_rejects_same_source_dest(acme, warehouse):
    f = forms.StockTransferForm(
        data={
            'source_warehouse': warehouse.pk,
            'destination_warehouse': warehouse.pk,
            'requested_date': timezone.now().date().isoformat(),
        },
        tenant=acme,
    )
    assert not f.is_valid()


def test_adjustment_form_requires_reason_notes(acme, warehouse):
    f = forms.StockAdjustmentForm(
        data={'warehouse': warehouse.pk, 'reason': 'damage', 'reason_notes': '   '},
        tenant=acme,
    )
    assert not f.is_valid()
    assert 'reason_notes' in f.errors


def test_cycle_count_plan_form_rejects_duplicate(acme, warehouse):
    inv_models.CycleCountPlan.objects.create(
        tenant=acme, name='daily-A', warehouse=warehouse, frequency='daily',
    )
    f = forms.CycleCountPlanForm(
        data={
            'name': 'daily-A', 'warehouse': warehouse.pk,
            'frequency': 'daily', 'is_active': True,
        },
        tenant=acme,
    )
    assert not f.is_valid()
    assert 'name' in f.errors
