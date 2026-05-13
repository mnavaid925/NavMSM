"""Workflow tests for SalesOrder (17.2)."""
from decimal import Decimal

import pytest

from apps.sales.models import (
    SalesOrder,
    SalesOrderApprovalLog,
    SalesOrderLine,
    SalesOrderRevision,
)
from apps.sales.services.credit import check_credit
from apps.sales.services.workflow import (
    cancel_sales_order,
    confirm_sales_order,
    hold_sales_order,
    release_credit_hold,
    resume_sales_order,
    revise_sales_order,
    submit_sales_order,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def product(tenant_a):
    from apps.plm.models import Product
    return Product.objects.create(tenant=tenant_a, name='Widget', code='WG-001')


@pytest.fixture
def so(tenant_a, customer):
    return SalesOrder.objects.create(
        tenant=tenant_a, customer=customer, currency='USD', payment_terms='net30',
    )


@pytest.fixture
def so_with_line(tenant_a, so, product):
    SalesOrderLine.objects.create(
        tenant=tenant_a, sales_order=so, product=product,
        qty_ordered=Decimal('10'), unit_price=Decimal('100'),
    )
    so.recompute_totals()
    so.refresh_from_db()
    return so


def test_so_auto_code(tenant_a, customer):
    s = SalesOrder.objects.create(tenant=tenant_a, customer=customer)
    assert s.code.startswith('SO-')


def test_so_line_recomputes_total(tenant_a, so, product):
    line = SalesOrderLine.objects.create(
        tenant=tenant_a, sales_order=so, product=product,
        qty_ordered=Decimal('5'), unit_price=Decimal('20'),
        line_discount_pct=Decimal('10'),
    )
    # 5*20 = 100, discount 10% = 10, line_total = 90
    assert line.line_total == Decimal('90.00')
    assert line.line_discount == Decimal('10.00')


def test_so_recompute_totals(tenant_a, so_with_line):
    assert so_with_line.subtotal > Decimal('0')
    assert so_with_line.grand_total > Decimal('0')


def test_workflow_submit_then_confirm(tenant_a, so_with_line):
    result = submit_sales_order(so_with_line)
    so_with_line.refresh_from_db()
    # Credit limit of 10k vs grand_total 1000 -> should pass
    assert result.status == 'ok'
    assert so_with_line.status == 'submitted'
    confirm_sales_order(so_with_line)
    so_with_line.refresh_from_db()
    assert so_with_line.status == 'confirmed'


def test_workflow_logs_each_action(tenant_a, so_with_line):
    submit_sales_order(so_with_line)
    so_with_line.refresh_from_db()
    confirm_sales_order(so_with_line)
    assert SalesOrderApprovalLog.objects.filter(sales_order=so_with_line).count() >= 2


def test_credit_check_over_limit(tenant_a, customer, so_with_line):
    customer.credit_limit = Decimal('500')
    customer.save()
    result = check_credit(customer, so_with_line.grand_total)
    assert result.is_hold
    assert result.status == 'hold_credit_limit'


def test_blacklisted_customer_blocks_credit(tenant_a, customer, so_with_line):
    customer.status = 'blacklisted'
    customer.save()
    result = check_credit(customer, Decimal('1'))
    assert result.is_hold
    assert result.status == 'hold_blacklist'


def test_submit_with_overlimit_triggers_credit_check_status(tenant_a, customer, so_with_line):
    customer.credit_limit = Decimal('1')
    customer.save()
    submit_sales_order(so_with_line)
    so_with_line.refresh_from_db()
    assert so_with_line.status == 'credit_check'
    assert so_with_line.credit_hold is True


def test_release_credit_hold(tenant_a, customer, so_with_line):
    customer.credit_limit = Decimal('1')
    customer.save()
    submit_sales_order(so_with_line)
    so_with_line.refresh_from_db()
    assert release_credit_hold(so_with_line) is True
    so_with_line.refresh_from_db()
    assert so_with_line.credit_hold is False


def test_cancel_and_hold_and_resume(tenant_a, so_with_line):
    submit_sales_order(so_with_line)
    so_with_line.refresh_from_db()
    hold_sales_order(so_with_line)
    so_with_line.refresh_from_db()
    assert so_with_line.status == 'on_hold'
    resume_sales_order(so_with_line)
    so_with_line.refresh_from_db()
    assert so_with_line.status == 'draft'


def test_cancel_terminal_state(tenant_a, so_with_line):
    cancel_sales_order(so_with_line)
    so_with_line.refresh_from_db()
    assert so_with_line.status == 'cancelled'
    with pytest.raises(ValueError):
        cancel_sales_order(so_with_line)


def test_revise_snapshots(tenant_a, so_with_line):
    submit_sales_order(so_with_line)
    so_with_line.refresh_from_db()
    confirm_sales_order(so_with_line)
    so_with_line.refresh_from_db()
    rev = revise_sales_order(so_with_line, reason='customer price renegotiated')
    assert rev.version_no == 1
    assert rev.snapshot_json['header']['code'] == so_with_line.code
    assert len(rev.snapshot_json['lines']) == 1


def test_revise_increments_version(tenant_a, so_with_line):
    submit_sales_order(so_with_line)
    so_with_line.refresh_from_db()
    confirm_sales_order(so_with_line)
    so_with_line.refresh_from_db()
    r1 = revise_sales_order(so_with_line)
    r2 = revise_sales_order(so_with_line)
    assert r2.version_no == r1.version_no + 1


def test_mto_auto_spawns_production_order(tenant_a, so, product):
    line = SalesOrderLine.objects.create(
        tenant=tenant_a, sales_order=so, product=product,
        qty_ordered=Decimal('5'), unit_price=Decimal('100'),
        is_make_to_order=True,
    )
    so.recompute_totals()
    so.refresh_from_db()
    submit_sales_order(so)
    so.refresh_from_db()
    confirm_sales_order(so)
    so.refresh_from_db()
    # Signal should have spawned a ProductionOrder
    from apps.pps.models import ProductionOrder
    pos = ProductionOrder.all_objects.filter(source_sales_line=line)
    assert pos.exists()
    po = pos.first()
    assert po.quantity == Decimal('5')
    assert po.status == 'planned'


def test_mto_signal_is_idempotent(tenant_a, so, product):
    """Saving an already-confirmed SO again must not spawn duplicate POs."""
    line = SalesOrderLine.objects.create(
        tenant=tenant_a, sales_order=so, product=product,
        qty_ordered=Decimal('3'), unit_price=Decimal('50'),
        is_make_to_order=True,
    )
    so.recompute_totals()
    submit_sales_order(so)
    so.refresh_from_db()
    confirm_sales_order(so)
    so.refresh_from_db()
    so.save()  # re-trigger signal
    so.save()
    from apps.pps.models import ProductionOrder
    assert ProductionOrder.all_objects.filter(source_sales_line=line).count() == 1


def test_non_mto_line_does_not_spawn_po(tenant_a, so, product):
    line = SalesOrderLine.objects.create(
        tenant=tenant_a, sales_order=so, product=product,
        qty_ordered=Decimal('2'), unit_price=Decimal('50'),
        is_make_to_order=False,
    )
    so.recompute_totals()
    submit_sales_order(so)
    so.refresh_from_db()
    confirm_sales_order(so)
    so.refresh_from_db()
    from apps.pps.models import ProductionOrder
    assert not ProductionOrder.all_objects.filter(source_sales_line=line).exists()
