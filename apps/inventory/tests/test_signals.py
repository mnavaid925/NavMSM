"""Signal tests: audit-log + MES ProductionReport auto-emit."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.bom.models import BillOfMaterials
from apps.inventory import models as inv_models
from apps.mes.models import (
    MESWorkOrder, MESWorkOrderOperation, ProductionReport, ShopFloorOperator,
)
from apps.pps.models import (
    ProductionOrder, Routing, RoutingOperation, WorkCenter,
)
from apps.tenants.models import TenantAuditLog


pytestmark = pytest.mark.django_db


# ---------- Audit ----------

def test_warehouse_create_writes_audit(acme):
    inv_models.Warehouse.objects.create(tenant=acme, code='WH-A', name='A')
    assert TenantAuditLog.objects.filter(
        tenant=acme, action='inventory.warehouse.created',
    ).exists()


def test_warehouse_active_change_writes_audit(acme, warehouse):
    warehouse.is_active = False
    warehouse.save()
    assert TenantAuditLog.objects.filter(
        tenant=acme, action='inventory.warehouse.active_changed',
    ).exists()


def test_grn_create_writes_audit(acme, warehouse):
    inv_models.GoodsReceiptNote.objects.create(tenant=acme, warehouse=warehouse)
    assert TenantAuditLog.objects.filter(
        tenant=acme, action='inventory.grn.created',
    ).exists()


def test_grn_status_change_writes_audit(acme, warehouse):
    g = inv_models.GoodsReceiptNote.objects.create(tenant=acme, warehouse=warehouse)
    g.status = 'received'
    g.save()
    assert TenantAuditLog.objects.filter(
        tenant=acme, action='inventory.grn.received',
    ).exists()


def test_transfer_create_writes_audit(acme, warehouse):
    wh2 = inv_models.Warehouse.objects.create(tenant=acme, code='WH2', name='B')
    inv_models.StockTransfer.objects.create(
        tenant=acme, source_warehouse=warehouse, destination_warehouse=wh2,
    )
    assert TenantAuditLog.objects.filter(
        tenant=acme, action='inventory.transfer.created',
    ).exists()


def test_adjustment_create_writes_audit(acme, warehouse):
    inv_models.StockAdjustment.objects.create(
        tenant=acme, warehouse=warehouse, reason='damage', reason_notes='x',
    )
    assert TenantAuditLog.objects.filter(
        tenant=acme, action='inventory.adjustment.created',
    ).exists()


def test_cycle_count_create_writes_audit(acme, warehouse):
    inv_models.CycleCountSheet.objects.create(tenant=acme, warehouse=warehouse)
    assert TenantAuditLog.objects.filter(
        tenant=acme, action='inventory.cycle_count.created',
    ).exists()


# ---------- MES ProductionReport auto-emit ----------

@pytest.fixture
def mes_setup(db, acme, fg_product, warehouse, bin_a, storage_zone, acme_admin):
    """Build the minimum MES + PPS + BOM scaffolding to fire ProductionReport."""
    wc = WorkCenter.objects.create(
        tenant=acme, code='WC-T', name='WC', work_center_type='cell',
        capacity_per_hour=Decimal('1'), efficiency_pct=Decimal('100'),
        cost_per_hour=Decimal('1'), is_active=True,
    )
    routing = Routing.objects.create(
        tenant=acme, product=fg_product, version='A', routing_number='ROUT-T',
        status='active', is_default=True, created_by=acme_admin,
    )
    op = RoutingOperation.objects.create(
        tenant=acme, routing=routing, sequence=10, operation_name='Make',
        work_center=wc, setup_minutes=Decimal('1'),
        run_minutes_per_unit=Decimal('1'),
        queue_minutes=Decimal('0'), move_minutes=Decimal('0'),
    )
    bom = BillOfMaterials.objects.create(
        tenant=acme, product=fg_product, bom_type='mbom',
        version='1', revision='A', status='released', is_default=True,
        created_by=acme_admin,
    )
    po = ProductionOrder.objects.create(
        tenant=acme, order_number='PO-T-1', product=fg_product,
        routing=routing, bom=bom, quantity=Decimal('10'),
        status='in_progress', priority='normal', scheduling_method='forward',
        requested_start=timezone.now(), requested_end=timezone.now() + timedelta(days=1),
    )
    wo = MESWorkOrder.objects.create(
        tenant=acme, wo_number='WO-T-1', production_order=po,
        product=fg_product, quantity_to_build=Decimal('10'),
        status='in_progress', priority='normal',
        dispatched_by=acme_admin, dispatched_at=timezone.now(),
    )
    wo_op = MESWorkOrderOperation.objects.create(
        tenant=acme, work_order=wo, sequence=10, operation_name='Make',
        work_center=wc, routing_operation=op,
        setup_minutes=Decimal('1'), run_minutes_per_unit=Decimal('1'),
        planned_minutes=Decimal('11'), status='running',
    )
    operator = ShopFloorOperator.objects.create(
        tenant=acme, user=acme_admin, badge_number='B-T1', is_active=True,
    )
    return {'wo': wo, 'wo_op': wo_op, 'operator': operator}


def test_production_report_auto_emits_movement(acme, mes_setup, warehouse, bin_a, fg_product, acme_admin):
    """A ProductionReport with good_qty>0 auto-creates a production_in StockMovement."""
    pr = ProductionReport.objects.create(
        tenant=acme,
        work_order_operation=mes_setup['wo_op'],
        good_qty=Decimal('5'), scrap_qty=Decimal('0'), rework_qty=Decimal('0'),
        reported_by=acme_admin, reported_at=timezone.now(),
    )
    mv = inv_models.StockMovement.all_objects.filter(production_report=pr).first()
    assert mv is not None
    assert mv.movement_type == 'production_in'
    assert mv.qty == Decimal('5')
    assert mv.product == fg_product
    item = inv_models.StockItem.all_objects.get(tenant=acme, product=fg_product, bin=bin_a)
    assert item.qty_on_hand == Decimal('5')


def test_production_report_skipped_when_zero_good_qty(acme, mes_setup, warehouse, bin_a, acme_admin):
    pr = ProductionReport.objects.create(
        tenant=acme,
        work_order_operation=mes_setup['wo_op'],
        good_qty=Decimal('0'), scrap_qty=Decimal('1'), rework_qty=Decimal('0'),
        scrap_reason='material_defect',
        reported_by=acme_admin, reported_at=timezone.now(),
    )
    assert not inv_models.StockMovement.all_objects.filter(production_report=pr).exists()


def test_production_report_skipped_without_default_warehouse(acme, mes_setup, warehouse, fg_product, acme_admin):
    """No DEFAULT warehouse -> auto-emit silently skips. (Toggle is_default off.)"""
    warehouse.is_default = False
    warehouse.save()
    pr = ProductionReport.objects.create(
        tenant=acme,
        work_order_operation=mes_setup['wo_op'],
        good_qty=Decimal('3'), scrap_qty=Decimal('0'), rework_qty=Decimal('0'),
        reported_by=acme_admin, reported_at=timezone.now(),
    )
    assert not inv_models.StockMovement.all_objects.filter(production_report=pr).exists()


def test_production_report_delete_reverses_movement(acme, mes_setup, warehouse, bin_a, fg_product, acme_admin):
    pr = ProductionReport.objects.create(
        tenant=acme,
        work_order_operation=mes_setup['wo_op'],
        good_qty=Decimal('4'), scrap_qty=Decimal('0'), rework_qty=Decimal('0'),
        reported_by=acme_admin, reported_at=timezone.now(),
    )
    item_before = inv_models.StockItem.all_objects.get(tenant=acme, product=fg_product, bin=bin_a)
    assert item_before.qty_on_hand == Decimal('4')
    pr.delete()
    item_after = inv_models.StockItem.all_objects.get(tenant=acme, product=fg_product, bin=bin_a)
    assert item_after.qty_on_hand == Decimal('0')
