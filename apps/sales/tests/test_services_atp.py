"""ATP service tests (17.3)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.sales.services.atp import compute_atp


pytestmark = pytest.mark.django_db


@pytest.fixture
def product(tenant_a):
    from apps.plm.models import Product
    return Product.objects.create(tenant=tenant_a, name='Widget', code='WG-001')


def test_atp_no_stock_no_po(tenant_a, product):
    """No on-hand and no open POs -> no_stock."""
    r = compute_atp(
        tenant=tenant_a, product=product,
        requested_qty=Decimal('10'),
        requested_date=date.today(),
        method='stock_only',
    )
    assert r.result_status == 'no_stock'
    assert r.available_qty == Decimal('0')


def test_atp_fully_promised_with_stock(tenant_a, product):
    """If StockItem exists with enough qty, fully_promised."""
    from apps.inventory.models import Warehouse, Zone, StorageBin, StockItem
    wh = Warehouse.objects.create(tenant=tenant_a, code='WH1', name='Main')
    zone = Zone.objects.create(tenant=tenant_a, warehouse=wh, code='Z1', name='Zone 1')
    bin_ = StorageBin.objects.create(tenant=tenant_a, zone=zone, code='B1')
    StockItem.objects.create(
        tenant=tenant_a, product=product, bin=bin_,
        qty_on_hand=Decimal('50'),
    )
    r = compute_atp(
        tenant=tenant_a, product=product,
        requested_qty=Decimal('10'),
        requested_date=date.today(),
        method='stock_only',
    )
    assert r.result_status == 'fully_promised'
    assert r.available_qty == Decimal('50')


def test_atp_partial_with_committed_orders(tenant_a, product, customer):
    """on-hand 10, committed 8 (1 open SO of 8) -> available 2."""
    from apps.inventory.models import Warehouse, Zone, StorageBin, StockItem
    from apps.sales.models import SalesOrder, SalesOrderLine
    wh = Warehouse.objects.create(tenant=tenant_a, code='WH1', name='Main')
    zone = Zone.objects.create(tenant=tenant_a, warehouse=wh, code='Z1', name='Zone 1')
    bin_ = StorageBin.objects.create(tenant=tenant_a, zone=zone, code='B1')
    StockItem.objects.create(tenant=tenant_a, product=product, bin=bin_, qty_on_hand=Decimal('10'))

    so = SalesOrder.objects.create(tenant=tenant_a, customer=customer, status='confirmed')
    SalesOrderLine.objects.create(
        tenant=tenant_a, sales_order=so, product=product,
        qty_ordered=Decimal('8'), unit_price=Decimal('5'),
    )
    r = compute_atp(
        tenant=tenant_a, product=product,
        requested_qty=Decimal('5'),
        requested_date=date.today(),
        method='stock_only',
    )
    # 10 on-hand - 8 committed = 2 available
    assert r.available_qty == Decimal('2')
    assert r.result_status == 'partially_promised'
