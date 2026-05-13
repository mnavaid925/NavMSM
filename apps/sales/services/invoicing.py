"""Invoicing service (17.4).

`generate_invoice_from_shipment` is idempotent on `SalesInvoice.shipment`
- calling it twice for the same shipment returns the existing draft
rather than creating a duplicate.

`issue_invoice` and `mark_invoice_paid` are the only sanctioned paths
for status transitions on SalesInvoice. Both use a conditional UPDATE
WHERE status=<expected> so the credit_used denorm adjustment runs at
most once per real transition - that is also why the previous
`post_save` signal in `apps/sales/signals.py` was removed (it could
fire on any save of a row already in the target state).
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone


@transaction.atomic
def generate_invoice_from_shipment(shipment, *, issued_by=None):
    """Build a draft SalesInvoice from a delivered Shipment + its lines.

    Returns the (possibly pre-existing) SalesInvoice.
    """
    from apps.sales.models import SalesInvoice, SalesInvoiceLine

    existing = SalesInvoice.objects.filter(
        tenant=shipment.tenant, shipment=shipment,
    ).first()
    if existing:
        return existing

    invoice = SalesInvoice.objects.create(
        tenant=shipment.tenant,
        sales_order=shipment.sales_order,
        shipment=shipment,
        invoice_date=timezone.now().date(),
        payment_terms=shipment.sales_order.payment_terms,
        status='draft',
        issued_by=issued_by,
    )
    for sl in shipment.shipment_lines.all():
        ol = sl.order_line
        SalesInvoiceLine.objects.create(
            tenant=shipment.tenant,
            invoice=invoice,
            shipment_line=sl,
            description=f'{ol.product.code} - {ol.product.name}',
            qty=sl.qty_shipped or sl.qty_to_ship,
            unit_price=ol.unit_price,
            line_discount_pct=ol.line_discount_pct,
            line_tax_pct=ol.line_tax_pct,
        )
    invoice.recompute_totals()
    return invoice


@transaction.atomic
def issue_invoice(invoice, *, performed_by=None):
    """draft -> issued. Atomically adds grand_total to customer.credit_used.

    Uses a conditional UPDATE WHERE status='draft' so the credit adjustment
    happens exactly once even on concurrent calls.
    """
    from apps.sales.models import Customer, SalesInvoice

    if invoice.status != 'draft':
        raise ValueError(f'Cannot issue from status {invoice.status}.')

    rows = (
        SalesInvoice.all_objects
        .filter(pk=invoice.pk, status='draft')
        .update(status='issued', updated_at=timezone.now())
    )
    if not rows:
        raise ValueError('Concurrent update detected; please refresh.')

    if invoice.sales_order_id:
        Customer.all_objects.filter(
            pk=invoice.sales_order.customer_id,
        ).update(
            credit_used=F('credit_used') + (invoice.grand_total or Decimal('0')),
        )
    invoice.refresh_from_db()
    return invoice


@transaction.atomic
def mark_invoice_paid(invoice, *, amount=None, performed_by=None):
    """issued | overdue -> paid. Bumps amount_paid + flips status.

    Refuses on draft (use `issue_invoice` first) and on cancelled.
    Atomically decrements customer.credit_used by `amount` (defaults to
    grand_total), gated by a conditional UPDATE WHERE status in
    (issued, overdue) so re-saves of an already-paid invoice do not
    double-decrement.
    """
    from apps.sales.models import Customer, SalesInvoice

    if invoice.status == 'paid':
        return invoice
    if invoice.status == 'cancelled':
        raise ValueError('Cannot pay a cancelled invoice.')
    if invoice.status not in ('issued', 'overdue'):
        raise ValueError(
            f'Cannot mark paid from status {invoice.status}; issue the invoice first.',
        )

    amount = Decimal(amount) if amount is not None else (invoice.grand_total or Decimal('0'))
    new_paid = (invoice.amount_paid or Decimal('0')) + amount

    rows = (
        SalesInvoice.all_objects
        .filter(pk=invoice.pk, status__in=('issued', 'overdue'))
        .update(status='paid', amount_paid=new_paid, updated_at=timezone.now())
    )
    if not rows:
        raise ValueError('Concurrent update detected; please refresh.')

    if invoice.sales_order_id:
        Customer.all_objects.filter(
            pk=invoice.sales_order.customer_id,
        ).update(
            credit_used=F('credit_used') - (invoice.grand_total or Decimal('0')),
        )
    invoice.refresh_from_db()
    return invoice
