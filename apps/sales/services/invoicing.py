"""Invoicing service (17.4).

`generate_invoice_from_shipment` is idempotent on `SalesInvoice.shipment`
- calling it twice for the same shipment returns the existing draft
rather than creating a duplicate.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
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
def mark_invoice_paid(invoice, *, amount=None, performed_by=None):
    """draft / issued -> paid. Bumps amount_paid + flips status."""
    if invoice.status == 'paid':
        return invoice
    if invoice.status in ('cancelled', 'overdue'):
        # `overdue` is a label only; allow paying an overdue invoice
        if invoice.status == 'cancelled':
            raise ValueError('Cannot pay a cancelled invoice.')
    amount = Decimal(amount) if amount is not None else (invoice.grand_total or Decimal('0'))
    invoice.amount_paid = (invoice.amount_paid or Decimal('0')) + amount
    invoice.status = 'paid'
    invoice.save(update_fields=['amount_paid', 'status', 'updated_at'])
    return invoice
