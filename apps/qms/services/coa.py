"""Certificate of Analysis payload builder.

Pure: returns a dict with everything the CoA template needs to render.
The actual HTML rendering (and browser-print-to-PDF) is done in the view
layer.

A future ``xhtml2pdf`` / ``WeasyPrint`` integration can re-use the same
payload and return a real PDF. Keeping this layer pure makes that
swappable without touching the call site.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal


def build_coa_payload(inspection, *, issued_at: datetime, issued_by=None,
                      customer_name: str = '', customer_reference: str = '',
                      coa_number: str = ''):
    """Return a dict shaped for the CoA template.

    ``inspection`` is a ``FinalInspection`` instance. We deliberately accept
    the ORM instance here (rather than splitting into raw fields) because
    the template needs many fields in stable shapes; passing the instance
    keeps the caller terse and the function easy to test against a fixture.
    """
    plan = inspection.plan
    product = plan.product if plan else None
    work_order = inspection.work_order
    tenant = inspection.tenant

    # Pull all linked test results in spec order.
    rows = []
    for r in inspection.results.select_related('spec').all():
        rows.append({
            'sequence': r.spec.sequence,
            'test_name': r.spec.test_name,
            'method': r.spec.get_test_method_display(),
            'spec_target': str(r.spec.nominal) if r.spec.nominal is not None else (
                r.spec.expected_result or ''
            ),
            'spec_usl': str(r.spec.usl) if r.spec.usl is not None else '',
            'spec_lsl': str(r.spec.lsl) if r.spec.lsl is not None else '',
            'unit_of_measure': r.spec.unit_of_measure or '',
            'measured': (str(r.measured_value) if r.measured_value is not None
                         else r.measured_text or ''),
            'is_pass': r.is_pass,
            'is_critical': r.spec.is_critical,
            'notes': r.notes,
        })
    rows.sort(key=lambda d: d['sequence'])

    accept_qty = inspection.accepted_qty or Decimal('0')
    reject_qty = inspection.rejected_qty or Decimal('0')
    tested_qty = inspection.quantity_tested or Decimal('0')

    return {
        'tenant': {
            'name': getattr(tenant, 'name', ''),
            'address': getattr(tenant, 'address', ''),
            'email': getattr(tenant, 'email', ''),
            'phone': getattr(tenant, 'phone', ''),
        },
        'coa_number': coa_number,
        'issued_at': issued_at,
        'issued_by': (issued_by.get_full_name() or issued_by.username) if issued_by else '',
        'customer_name': customer_name,
        'customer_reference': customer_reference,
        'product': {
            'sku': getattr(product, 'sku', ''),
            'name': getattr(product, 'name', ''),
            'unit_of_measure': getattr(product, 'unit_of_measure', ''),
        },
        'inspection': {
            'number': inspection.inspection_number,
            'lot_number': inspection.lot_number,
            'tested_qty': str(tested_qty),
            'accepted_qty': str(accept_qty),
            'rejected_qty': str(reject_qty),
            'status': inspection.get_status_display(),
            'inspected_at': inspection.inspected_at,
            'deviation_notes': inspection.deviation_notes,
        },
        'work_order': {
            'wo_number': getattr(work_order, 'wo_number', ''),
            'product_sku': getattr(work_order, 'product', None) and work_order.product.sku,
        },
        'plan': {
            'name': getattr(plan, 'name', ''),
            'version': getattr(plan, 'version', ''),
        },
        'results': rows,
        'all_passed': all(r['is_pass'] for r in rows) if rows else False,
        'released_with_deviation': inspection.status == 'released_with_deviation',
    }
