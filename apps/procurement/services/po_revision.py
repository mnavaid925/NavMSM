"""Snapshot a Purchase Order + its lines into an immutable JSON revision.

Pure function: given a PurchaseOrder ORM instance, return a dict capturing
the header + every line. Used by the Revise action and the seeded data path.
"""
from decimal import Decimal


def _decimal(v):
    """Render Decimal as plain string so JSONField stays portable."""
    return str(v) if isinstance(v, Decimal) else v


def snapshot_po(po):
    """Build a JSON-serialisable snapshot of a PurchaseOrder + lines."""
    return {
        'po_number': po.po_number,
        'supplier_id': po.supplier_id,
        'supplier_code': po.supplier.code if po.supplier_id else None,
        'order_date': po.order_date.isoformat() if po.order_date else None,
        'required_date': po.required_date.isoformat() if po.required_date else None,
        'currency': po.currency,
        'status': po.status,
        'priority': po.priority,
        'subtotal': _decimal(po.subtotal),
        'tax_total': _decimal(po.tax_total),
        'discount_total': _decimal(po.discount_total),
        'grand_total': _decimal(po.grand_total),
        'lines': [
            {
                'line_number': line.line_number,
                'product_id': line.product_id,
                'product_sku': line.product.sku if line.product_id else None,
                'description': line.description,
                'quantity': _decimal(line.quantity),
                'unit_of_measure': line.unit_of_measure,
                'unit_price': _decimal(line.unit_price),
                'tax_pct': _decimal(line.tax_pct),
                'discount_pct': _decimal(line.discount_pct),
                'line_total': _decimal(line.line_total),
            }
            for line in po.lines.all().order_by('line_number')
        ],
    }


def next_revision_number(po):
    """Return the next sequential revision number for a PO (1-based)."""
    from apps.procurement.models import PurchaseOrderRevision

    last = (
        PurchaseOrderRevision.all_objects
        .filter(po=po)
        .order_by('-revision_number')
        .first()
    )
    return (last.revision_number + 1) if last else 1
