"""View smoke tests + workflow."""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.inventory import models as inv_models


pytestmark = pytest.mark.django_db


# ---------- Smoke ----------

@pytest.mark.parametrize('name', [
    'inventory:index',
    'inventory:warehouse_list',
    'inventory:zone_list',
    'inventory:bin_list',
    'inventory:stockitem_list',
    'inventory:grn_list',
    'inventory:movement_list',
    'inventory:transfer_list',
    'inventory:adjustment_list',
    'inventory:cc_plan_list',
    'inventory:cc_sheet_list',
    'inventory:lot_list',
    'inventory:serial_list',
])
def test_dashboard_and_list_pages_render(admin_client, warehouse, name):
    resp = admin_client.get(reverse(name))
    assert resp.status_code == 200


def test_warehouse_create_post(admin_client, acme):
    resp = admin_client.post(
        reverse('inventory:warehouse_create'),
        {'code': 'NEW', 'name': 'New WH', 'is_active': 'on'},
    )
    assert resp.status_code == 302
    assert inv_models.Warehouse.objects.filter(tenant=acme, code='NEW').exists()


def test_warehouse_edit_post(admin_client, warehouse):
    resp = admin_client.post(
        reverse('inventory:warehouse_edit', args=[warehouse.pk]),
        {'code': warehouse.code, 'name': 'Renamed', 'is_active': 'on'},
    )
    assert resp.status_code == 302
    warehouse.refresh_from_db()
    assert warehouse.name == 'Renamed'


def test_warehouse_delete_post(admin_client, acme):
    wh = inv_models.Warehouse.objects.create(tenant=acme, code='DEL', name='Del')
    resp = admin_client.post(reverse('inventory:warehouse_delete', args=[wh.pk]))
    assert resp.status_code == 302
    assert not inv_models.Warehouse.objects.filter(pk=wh.pk).exists()


# ---------- GRN workflow ----------

def test_grn_create_post(admin_client, acme, warehouse):
    resp = admin_client.post(
        reverse('inventory:grn_create'),
        {
            'warehouse': warehouse.pk, 'supplier_name': 'Acme Supplier',
            'po_reference': 'PO-1', 'received_date': '2026-05-03',
        },
    )
    assert resp.status_code == 302
    assert inv_models.GoodsReceiptNote.objects.filter(tenant=acme).exists()


def test_grn_receive_generates_putaway(admin_client, acme, warehouse, fg_product, receiving_zone, bin_a):
    grn = inv_models.GoodsReceiptNote.objects.create(tenant=acme, warehouse=warehouse)
    inv_models.GRNLine.objects.create(
        tenant=acme, grn=grn, product=fg_product,
        receiving_zone=receiving_zone, expected_qty=Decimal('5'),
        received_qty=Decimal('5'),
    )
    resp = admin_client.post(reverse('inventory:grn_receive', args=[grn.pk]))
    assert resp.status_code == 302
    grn.refresh_from_db()
    assert grn.status == 'putaway_pending'
    assert inv_models.PutawayTask.objects.filter(grn_line__grn=grn).exists()


def test_grn_cancel(admin_client, acme, warehouse):
    grn = inv_models.GoodsReceiptNote.objects.create(tenant=acme, warehouse=warehouse)
    resp = admin_client.post(reverse('inventory:grn_cancel', args=[grn.pk]))
    assert resp.status_code == 302
    grn.refresh_from_db()
    assert grn.status == 'cancelled'


# ---------- Movement create ----------

def test_movement_create_view_posts_movement(admin_client, acme, fg_product, bin_a):
    resp = admin_client.post(
        reverse('inventory:movement_create'),
        {
            'movement_type': 'receipt', 'product': fg_product.pk,
            'qty': '7', 'to_bin': bin_a.pk,
        },
    )
    assert resp.status_code == 302
    assert inv_models.StockMovement.objects.filter(
        tenant=acme, product=fg_product,
    ).exists()


# ---------- Transfer ship/receive ----------

def test_transfer_ship_and_receive_full_flow(admin_client, acme, warehouse, fg_product, bin_a, bin_b):
    # Seed source bin
    from apps.inventory.services.movements import post_movement
    post_movement(
        tenant=acme, movement_type='receipt', product=fg_product,
        qty=Decimal('10'), to_bin=bin_a,
    )
    wh2 = inv_models.Warehouse.objects.create(tenant=acme, code='WH2', name='B', is_active=True)
    tr = inv_models.StockTransfer.objects.create(
        tenant=acme, source_warehouse=warehouse, destination_warehouse=wh2,
    )
    inv_models.StockTransferLine.objects.create(
        tenant=acme, transfer=tr, product=fg_product,
        qty=Decimal('3'), source_bin=bin_a, destination_bin=bin_b,
    )

    resp = admin_client.post(reverse('inventory:transfer_ship', args=[tr.pk]))
    assert resp.status_code == 302
    tr.refresh_from_db()
    assert tr.status == 'in_transit'

    resp = admin_client.post(reverse('inventory:transfer_receive', args=[tr.pk]))
    assert resp.status_code == 302
    tr.refresh_from_db()
    assert tr.status == 'received'

    a_item = inv_models.StockItem.objects.get(tenant=acme, product=fg_product, bin=bin_a)
    b_item = inv_models.StockItem.objects.get(tenant=acme, product=fg_product, bin=bin_b)
    assert a_item.qty_on_hand == Decimal('7')
    assert b_item.qty_on_hand == Decimal('3')


# ---------- Adjustment post ----------

def test_adjustment_post_emits_movements(admin_client, acme, warehouse, bin_a, fg_product):
    from apps.inventory.services.movements import post_movement
    post_movement(
        tenant=acme, movement_type='receipt', product=fg_product,
        qty=Decimal('10'), to_bin=bin_a,
    )
    adj = inv_models.StockAdjustment.objects.create(
        tenant=acme, warehouse=warehouse, reason='damage', reason_notes='2 broken',
    )
    inv_models.StockAdjustmentLine.objects.create(
        tenant=acme, adjustment=adj, bin=bin_a, product=fg_product,
        system_qty=Decimal('10'), actual_qty=Decimal('8'),
    )
    resp = admin_client.post(reverse('inventory:adjustment_post', args=[adj.pk]))
    assert resp.status_code == 302
    adj.refresh_from_db()
    assert adj.status == 'posted'
    item = inv_models.StockItem.objects.get(tenant=acme, product=fg_product, bin=bin_a)
    assert item.qty_on_hand == Decimal('8')


# ---------- Cycle count workflow ----------

def test_cycle_count_start_and_reconcile(admin_client, acme, warehouse, bin_a, fg_product):
    from apps.inventory.services.movements import post_movement
    post_movement(
        tenant=acme, movement_type='receipt', product=fg_product,
        qty=Decimal('10'), to_bin=bin_a,
    )
    sheet = inv_models.CycleCountSheet.objects.create(tenant=acme, warehouse=warehouse)
    inv_models.CycleCountLine.objects.create(
        tenant=acme, sheet=sheet, bin=bin_a, product=fg_product,
        system_qty=Decimal('10'), counted_qty=Decimal('9'),
    )
    resp = admin_client.post(reverse('inventory:cc_sheet_start', args=[sheet.pk]))
    assert resp.status_code == 302
    sheet.refresh_from_db()
    assert sheet.status == 'counting'

    resp = admin_client.post(reverse('inventory:cc_sheet_reconcile', args=[sheet.pk]))
    assert resp.status_code == 302
    sheet.refresh_from_db()
    assert sheet.status == 'reconciled'
    item = inv_models.StockItem.objects.get(tenant=acme, product=fg_product, bin=bin_a)
    assert item.qty_on_hand == Decimal('9')
