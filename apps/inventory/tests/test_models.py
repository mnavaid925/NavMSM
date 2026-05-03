"""Model invariants and validators."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from apps.inventory import models as inv_models


pytestmark = pytest.mark.django_db


def test_warehouse_unique_per_tenant_code(acme, globex):
    inv_models.Warehouse.objects.create(tenant=acme, code='WH1', name='A')
    inv_models.Warehouse.objects.create(tenant=globex, code='WH1', name='B')
    with pytest.raises(IntegrityError):
        inv_models.Warehouse.objects.create(tenant=acme, code='WH1', name='Dup')


def test_warehouse_zone_unique_per_warehouse(acme, warehouse):
    inv_models.WarehouseZone.objects.create(
        tenant=acme, warehouse=warehouse, code='Z1', name='Z1', zone_type='storage',
    )
    with pytest.raises(IntegrityError):
        inv_models.WarehouseZone.objects.create(
            tenant=acme, warehouse=warehouse, code='Z1', name='Z1d', zone_type='storage',
        )


def test_storage_bin_warehouse_property(bin_a, warehouse):
    assert bin_a.warehouse == warehouse


def test_grn_auto_number(acme, warehouse):
    g1 = inv_models.GoodsReceiptNote.objects.create(tenant=acme, warehouse=warehouse)
    g2 = inv_models.GoodsReceiptNote.objects.create(tenant=acme, warehouse=warehouse)
    assert g1.grn_number.startswith('GRN-')
    assert g2.grn_number.startswith('GRN-')
    assert g1.grn_number != g2.grn_number


def test_transfer_auto_number(acme, warehouse, globex_warehouse):
    # Two warehouses on different tenants — but transfer needs same tenant
    wh2 = inv_models.Warehouse.objects.create(tenant=acme, code='WH2', name='X')
    t = inv_models.StockTransfer.objects.create(
        tenant=acme, source_warehouse=warehouse, destination_warehouse=wh2,
    )
    assert t.transfer_number.startswith('TRF-')


def test_adjustment_auto_number(acme, warehouse):
    a = inv_models.StockAdjustment.objects.create(
        tenant=acme, warehouse=warehouse, reason='damage', reason_notes='Damaged in handling',
    )
    assert a.adjustment_number.startswith('ADJ-')


def test_cycle_count_sheet_auto_number(acme, warehouse):
    cc = inv_models.CycleCountSheet.objects.create(tenant=acme, warehouse=warehouse)
    assert cc.sheet_number.startswith('CC-')


def test_lot_unique_per_tenant_product(acme, fg_product):
    inv_models.Lot.objects.create(tenant=acme, product=fg_product, lot_number='L1')
    with pytest.raises(IntegrityError):
        inv_models.Lot.objects.create(tenant=acme, product=fg_product, lot_number='L1')


def test_lot_is_expiring_soon(acme, fg_product):
    today = timezone.now().date()
    l_soon = inv_models.Lot.objects.create(
        tenant=acme, product=fg_product, lot_number='L-soon',
        expiry_date=today + timedelta(days=10),
    )
    l_far = inv_models.Lot.objects.create(
        tenant=acme, product=fg_product, lot_number='L-far',
        expiry_date=today + timedelta(days=120),
    )
    l_none = inv_models.Lot.objects.create(
        tenant=acme, product=fg_product, lot_number='L-none',
    )
    assert l_soon.is_expiring_soon is True
    assert l_far.is_expiring_soon is False
    assert l_none.is_expiring_soon is False


def test_serial_unique_per_tenant_product(acme, fg_product):
    inv_models.SerialNumber.objects.create(
        tenant=acme, product=fg_product, serial_number='SN-1',
    )
    with pytest.raises(IntegrityError):
        inv_models.SerialNumber.objects.create(
            tenant=acme, product=fg_product, serial_number='SN-1',
        )


def test_stock_item_qty_available(acme, fg_product, bin_a):
    s = inv_models.StockItem.objects.create(
        tenant=acme, product=fg_product, bin=bin_a,
        qty_on_hand=Decimal('10'), qty_reserved=Decimal('3'),
    )
    assert s.qty_available == Decimal('7')


def test_stock_item_unique_combo(acme, fg_product, bin_a, lot):
    serial = inv_models.SerialNumber.objects.create(
        tenant=acme, product=fg_product, serial_number='SN-UNIQ',
    )
    inv_models.StockItem.objects.create(
        tenant=acme, product=fg_product, bin=bin_a, lot=lot, serial=serial,
        qty_on_hand=Decimal('5'),
    )
    with pytest.raises(IntegrityError):
        inv_models.StockItem.objects.create(
            tenant=acme, product=fg_product, bin=bin_a, lot=lot, serial=serial,
            qty_on_hand=Decimal('5'),
        )


def test_cycle_count_line_variance(acme, warehouse, bin_a, fg_product):
    sheet = inv_models.CycleCountSheet.objects.create(tenant=acme, warehouse=warehouse)
    l = inv_models.CycleCountLine.objects.create(
        tenant=acme, sheet=sheet, bin=bin_a, product=fg_product,
        system_qty=Decimal('10'), counted_qty=Decimal('8'),
    )
    assert l.variance == Decimal('-2')

    l2 = inv_models.CycleCountLine.objects.create(
        tenant=acme, sheet=sheet, bin=bin_a, product=fg_product,
        system_qty=Decimal('10'), counted_qty=None,
    )
    assert l2.variance is None


def test_adjustment_line_variance(acme, warehouse, bin_a, fg_product):
    adj = inv_models.StockAdjustment.objects.create(
        tenant=acme, warehouse=warehouse, reason='damage', reason_notes='x',
    )
    line = inv_models.StockAdjustmentLine.objects.create(
        tenant=acme, adjustment=adj, bin=bin_a, product=fg_product,
        system_qty=Decimal('10'), actual_qty=Decimal('12'),
    )
    assert line.variance == Decimal('2')


def test_movement_min_qty_validator(acme, fg_product, bin_a):
    mv = inv_models.StockMovement(
        tenant=acme, movement_type='receipt', product=fg_product,
        qty=Decimal('0'), to_bin=bin_a,
    )
    with pytest.raises(ValidationError):
        mv.full_clean()
