"""SalesInvoice idempotency + workflow tests (17.4)."""
from decimal import Decimal

import pytest

from apps.sales.models import (
    SalesInvoice, SalesOrder, SalesOrderLine, Shipment, ShipmentLine,
)
from apps.sales.services.invoicing import (
    generate_invoice_from_shipment,
    mark_invoice_paid,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def product(tenant_a):
    from apps.plm.models import Product
    return Product.objects.create(tenant=tenant_a, name='Widget', code='WG-001')


@pytest.fixture
def delivered_shipment(tenant_a, customer, product):
    so = SalesOrder.objects.create(
        tenant=tenant_a, customer=customer, status='confirmed', currency='USD',
    )
    line = SalesOrderLine.objects.create(
        tenant=tenant_a, sales_order=so, product=product,
        qty_ordered=Decimal('5'), unit_price=Decimal('100'),
    )
    so.recompute_totals()
    s = Shipment.objects.create(tenant=tenant_a, sales_order=so, status='in_transit')
    ShipmentLine.objects.create(
        tenant=tenant_a, shipment=s, order_line=line,
        qty_to_ship=Decimal('5'), qty_shipped=Decimal('5'),
    )
    s.status = 'delivered'
    s.save()
    return s


def test_invoice_auto_code_and_generation(tenant_a, delivered_shipment):
    inv = generate_invoice_from_shipment(delivered_shipment)
    assert inv.code.startswith('SINV-')
    assert inv.status == 'draft'
    assert inv.grand_total > Decimal('0')
    assert inv.lines.count() == 1


def test_invoice_generation_is_idempotent(tenant_a, delivered_shipment):
    inv1 = generate_invoice_from_shipment(delivered_shipment)
    inv2 = generate_invoice_from_shipment(delivered_shipment)
    assert inv1.pk == inv2.pk


def test_mark_invoice_paid_flips_status(tenant_a, delivered_shipment):
    inv = generate_invoice_from_shipment(delivered_shipment)
    inv.status = 'issued'
    inv.save()
    mark_invoice_paid(inv)
    inv.refresh_from_db()
    assert inv.status == 'paid'
    assert inv.amount_paid == inv.grand_total


def test_paid_invoice_drops_credit_used(tenant_a, customer, delivered_shipment):
    customer.credit_used = Decimal('500')
    customer.save()
    inv = generate_invoice_from_shipment(delivered_shipment)
    inv.status = 'paid'
    inv.save()  # triggers signal
    customer.refresh_from_db()
    # credit_used should drop by grand_total (5 * 100 = 500)
    assert customer.credit_used == Decimal('0')
