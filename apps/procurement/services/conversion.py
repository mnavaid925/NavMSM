"""Conversion bridges between modules.

- convert_pr_to_po(pr, user) -> PurchaseOrder
    Promotes an MRP-suggested purchase requisition into a draft PurchaseOrder.
    Idempotent: if the PR already has a converted PO, returns it.
- convert_quotation_to_po(quotation, user) -> PurchaseOrder
    Materialises an awarded SupplierQuotation into a draft PurchaseOrder.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone


@transaction.atomic
def convert_pr_to_po(pr, user, supplier=None):
    """Create a draft PurchaseOrder from an MRP requisition.

    The PR's ``converted_po`` FK is set so subsequent calls return the same PO.
    """
    from apps.procurement.models import PurchaseOrder, PurchaseOrderLine

    # Idempotence guard.
    existing = getattr(pr, 'converted_po', None)
    if existing is not None:
        return existing

    if supplier is None:
        # Fall back to first active supplier in the tenant - real usage will
        # set this explicitly from the form.
        from apps.procurement.models import Supplier
        supplier = Supplier.all_objects.filter(
            tenant=pr.tenant, is_active=True,
        ).first()
    if supplier is None:
        raise ValueError('Cannot convert PR: no supplier specified or available.')

    po = PurchaseOrder(
        tenant=pr.tenant,
        supplier=supplier,
        order_date=timezone.now().date(),
        required_date=pr.required_by_date,
        currency=supplier.currency,
        status='draft',
        priority='normal',
        notes=f'Auto-created from MRP requisition {pr.pr_number}.',
        created_by=user,
    )
    po.save()
    PurchaseOrderLine.all_objects.create(
        tenant=pr.tenant,
        po=po,
        line_number=1,
        product=pr.product,
        description=pr.product.name if pr.product_id else '',
        quantity=pr.quantity,
        unit_of_measure=getattr(pr.product, 'unit_of_measure', 'EA') or 'EA',
        unit_price=Decimal('0'),
        required_date=pr.required_by_date,
    )
    po.refresh_from_db()
    po.recompute_totals()

    # Stamp the source PR. Use update() so we bypass signals - the MRP module
    # already audits these fields via its own signal stack.
    type(pr).all_objects.filter(pk=pr.pk).update(
        converted_po=po,
        converted_at=timezone.now(),
        converted_reference=po.po_number,
        status='converted',
    )
    return po


@transaction.atomic
def convert_quotation_to_po(quotation, user):
    """Create a draft PurchaseOrder from an awarded SupplierQuotation."""
    from apps.procurement.models import PurchaseOrder, PurchaseOrderLine

    po = PurchaseOrder(
        tenant=quotation.tenant,
        supplier=quotation.supplier,
        order_date=timezone.now().date(),
        required_date=None,
        currency=quotation.currency,
        payment_terms=quotation.payment_terms,
        delivery_terms=quotation.delivery_terms,
        status='draft',
        priority='normal',
        notes=f'Auto-created from quotation {quotation.quote_number}.',
        source_quotation=quotation,
        created_by=user,
    )
    po.save()
    line_number = 0
    for ql in quotation.lines.select_related('rfq_line').order_by('rfq_line__line_number'):
        line_number += 1
        rfq_line = ql.rfq_line
        PurchaseOrderLine.all_objects.create(
            tenant=quotation.tenant,
            po=po,
            line_number=line_number,
            product=rfq_line.product,
            description=rfq_line.description,
            quantity=rfq_line.quantity,
            unit_of_measure=rfq_line.unit_of_measure,
            unit_price=ql.unit_price,
            required_date=rfq_line.required_date,
        )
    po.refresh_from_db()
    po.recompute_totals()
    return po
