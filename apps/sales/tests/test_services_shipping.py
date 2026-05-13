"""Shipment workflow + delivery signal tests (17.4)."""
from decimal import Decimal

import pytest

from apps.sales.models import (
    SalesOrder, SalesOrderLine,
    Shipment, ShipmentLine,
)
from apps.sales.services.shipping import (
    confirm_delivery,
    dispatch_shipment,
    pack_shipment,
    pick_shipment,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def product(tenant_a):
    from apps.plm.models import Product
    return Product.objects.create(tenant=tenant_a, name='Widget', code='WG-001')


@pytest.fixture
def warehouse_with_bin(tenant_a):
    from apps.inventory.models import Warehouse, Zone, StorageBin
    wh = Warehouse.objects.create(tenant=tenant_a, code='WH1', name='Main')
    z = Zone.objects.create(tenant=tenant_a, warehouse=wh, code='Z1', name='Zone 1')
    bin_ = StorageBin.objects.create(tenant=tenant_a, zone=z, code='B1', is_default=True)
    return wh, bin_


@pytest.fixture
def stocked_item(tenant_a, product, warehouse_with_bin):
    wh, bin_ = warehouse_with_bin
    from apps.inventory.models import StockItem
    StockItem.objects.create(
        tenant=tenant_a, product=product, bin=bin_,
        qty_on_hand=Decimal('100'),
    )
    return wh, bin_


@pytest.fixture
def confirmed_so(tenant_a, customer, product):
    so = SalesOrder.objects.create(
        tenant=tenant_a, customer=customer, currency='USD',
        status='confirmed',
    )
    SalesOrderLine.objects.create(
        tenant=tenant_a, sales_order=so, product=product,
        qty_ordered=Decimal('10'), unit_price=Decimal('50'),
    )
    so.recompute_totals()
    so.refresh_from_db()
    return so


def test_shipment_auto_code(tenant_a, confirmed_so):
    s = Shipment.objects.create(tenant=tenant_a, sales_order=confirmed_so)
    assert s.code.startswith('SHP-')


def test_shipment_workflow_transitions(tenant_a, confirmed_so):
    s = Shipment.objects.create(tenant=tenant_a, sales_order=confirmed_so)
    pick_shipment(s)
    s.refresh_from_db()
    assert s.status == 'picked'
    pack_shipment(s)
    s.refresh_from_db()
    assert s.status == 'packed'
    dispatch_shipment(s)
    s.refresh_from_db()
    assert s.status == 'in_transit'


def test_shipment_delivered_emits_stock_movement(tenant_a, confirmed_so, stocked_item, product):
    wh, bin_ = stocked_item
    s = Shipment.objects.create(
        tenant=tenant_a, sales_order=confirmed_so, source_warehouse=wh,
    )
    line = confirmed_so.lines.first()
    sl = ShipmentLine.objects.create(
        tenant=tenant_a, shipment=s, order_line=line,
        qty_to_ship=Decimal('5'), qty_shipped=Decimal('5'),
        source_bin=bin_,
    )
    pick_shipment(s)
    s.refresh_from_db()
    pack_shipment(s)
    s.refresh_from_db()
    dispatch_shipment(s)
    s.refresh_from_db()
    confirm_delivery(s)
    s.refresh_from_db()
    assert s.status == 'delivered'

    from apps.inventory.models import StockMovement
    movs = StockMovement.all_objects.filter(source_shipment_line=sl)
    assert movs.count() == 1
    mv = movs.first()
    assert mv.movement_type == 'shipment_out'
    assert mv.qty == Decimal('5')


def test_shipment_delivery_signal_is_idempotent(tenant_a, confirmed_so, stocked_item):
    wh, bin_ = stocked_item
    s = Shipment.objects.create(
        tenant=tenant_a, sales_order=confirmed_so, source_warehouse=wh,
    )
    line = confirmed_so.lines.first()
    sl = ShipmentLine.objects.create(
        tenant=tenant_a, shipment=s, order_line=line,
        qty_to_ship=Decimal('2'), qty_shipped=Decimal('2'),
        source_bin=bin_,
    )
    pick_shipment(s); s.refresh_from_db()
    pack_shipment(s); s.refresh_from_db()
    dispatch_shipment(s); s.refresh_from_db()
    confirm_delivery(s); s.refresh_from_db()
    s.save()  # re-trigger signal
    s.save()
    from apps.inventory.models import StockMovement
    assert StockMovement.all_objects.filter(source_shipment_line=sl).count() == 1


def test_so_line_qty_shipped_denorm_updated(tenant_a, confirmed_so, stocked_item):
    wh, bin_ = stocked_item
    s = Shipment.objects.create(
        tenant=tenant_a, sales_order=confirmed_so, source_warehouse=wh,
    )
    line = confirmed_so.lines.first()
    ShipmentLine.objects.create(
        tenant=tenant_a, shipment=s, order_line=line,
        qty_to_ship=Decimal('7'), qty_shipped=Decimal('7'),
        source_bin=bin_,
    )
    pick_shipment(s); s.refresh_from_db()
    pack_shipment(s); s.refresh_from_db()
    dispatch_shipment(s); s.refresh_from_db()
    confirm_delivery(s); s.refresh_from_db()
    line.refresh_from_db()
    assert line.qty_shipped == Decimal('7')
