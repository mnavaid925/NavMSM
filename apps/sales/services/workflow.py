"""Sales-order workflow service (17.2).

Race-safe state transitions via conditional UPDATE - mirrors the
`apps/procurement/services/...` PO workflow pattern. Every transition
writes a `SalesOrderApprovalLog` row so the history is auditable.

The submit handler ALSO runs `check_credit` and toggles
`SalesOrder.credit_hold` so signals can branch into the confirmed path.
"""
from __future__ import annotations

import copy
from decimal import Decimal

from django.db import transaction
from django.utils import timezone


def _log(sales_order, action, from_status, to_status, performed_by=None, notes=''):
    from apps.sales.models import SalesOrderApprovalLog
    SalesOrderApprovalLog.objects.create(
        tenant=sales_order.tenant,
        sales_order=sales_order,
        action=action,
        from_status=from_status,
        to_status=to_status,
        performed_by=performed_by,
        notes=notes,
    )


def _conditional_update(sales_order, *, from_status, to_status, **extras):
    """Atomic UPDATE WHERE status=from_status. Returns True if row changed."""
    from apps.sales.models import SalesOrder
    extras['status'] = to_status
    extras['updated_at'] = timezone.now()
    rows = (
        SalesOrder.all_objects
        .filter(pk=sales_order.pk, status=from_status)
        .update(**extras)
    )
    if rows:
        sales_order.refresh_from_db()
    return bool(rows)


@transaction.atomic
def submit_sales_order(sales_order, performed_by=None, notes=''):
    """draft -> submitted, then run credit check.

    If the credit check fails, also flips credit_hold=True and moves
    status to 'credit_check'.
    """
    from apps.sales.services.credit import check_credit

    if sales_order.status != 'draft':
        raise ValueError(f'Cannot submit from status {sales_order.status}')

    ok = _conditional_update(sales_order, from_status='draft', to_status='submitted')
    if not ok:
        raise ValueError('Concurrent update detected; please refresh.')
    _log(sales_order, 'submit', 'draft', 'submitted', performed_by, notes)

    # Credit check - additive: the new SO grand_total is what the customer
    # would owe on top of credit_used.
    result = check_credit(sales_order.customer, sales_order.grand_total)
    if result.is_hold:
        _conditional_update(
            sales_order, from_status='submitted', to_status='credit_check',
            credit_hold=True,
        )
        _log(sales_order, 'credit_hold', 'submitted', 'credit_check',
             performed_by, result.message)
    return result


@transaction.atomic
def confirm_sales_order(sales_order, performed_by=None, notes=''):
    """submitted | credit_check -> confirmed.

    Refuses if credit_hold is True; release credit hold first.
    """
    if sales_order.credit_hold:
        raise ValueError('Cannot confirm while credit_hold is True. '
                         'Release the hold first.')
    if sales_order.status not in ('submitted', 'credit_check'):
        raise ValueError(f'Cannot confirm from status {sales_order.status}')

    ok = _conditional_update(
        sales_order, from_status=sales_order.status, to_status='confirmed',
        confirmed_by_id=getattr(performed_by, 'pk', None),
        confirmed_at=timezone.now(),
    )
    if not ok:
        raise ValueError('Concurrent update detected; please refresh.')
    _log(sales_order, 'confirm', sales_order.status, 'confirmed', performed_by, notes)


@transaction.atomic
def release_credit_hold(sales_order, performed_by=None, notes=''):
    """credit_check + credit_hold=True  ->  credit_check + credit_hold=False."""
    from apps.sales.models import SalesOrder
    rows = (
        SalesOrder.all_objects
        .filter(pk=sales_order.pk, credit_hold=True)
        .update(credit_hold=False, updated_at=timezone.now())
    )
    if not rows:
        return False
    sales_order.refresh_from_db()
    _log(sales_order, 'credit_release', sales_order.status, sales_order.status,
         performed_by, notes)
    return True


@transaction.atomic
def cancel_sales_order(sales_order, performed_by=None, notes=''):
    if not sales_order.can_cancel():
        raise ValueError(f'Cannot cancel from status {sales_order.status}')
    prev = sales_order.status
    ok = _conditional_update(
        sales_order, from_status=prev, to_status='cancelled',
        cancelled_at=timezone.now(),
    )
    if not ok:
        raise ValueError('Concurrent update detected; please refresh.')
    _log(sales_order, 'cancel', prev, 'cancelled', performed_by, notes)


@transaction.atomic
def hold_sales_order(sales_order, performed_by=None, notes=''):
    prev = sales_order.status
    if prev in ('on_hold', 'closed', 'cancelled'):
        raise ValueError(f'Cannot hold from status {prev}')
    ok = _conditional_update(sales_order, from_status=prev, to_status='on_hold')
    if not ok:
        raise ValueError('Concurrent update detected; please refresh.')
    _log(sales_order, 'hold', prev, 'on_hold', performed_by, notes)


@transaction.atomic
def resume_sales_order(sales_order, performed_by=None, notes=''):
    if sales_order.status != 'on_hold':
        raise ValueError(f'Cannot resume from status {sales_order.status}')
    ok = _conditional_update(sales_order, from_status='on_hold', to_status='draft')
    if not ok:
        raise ValueError('Concurrent update detected; please refresh.')
    _log(sales_order, 'resume', 'on_hold', 'draft', performed_by, notes)


@transaction.atomic
def revise_sales_order(sales_order, reason='', performed_by=None):
    """Snapshot the current header + lines as an immutable SalesOrderRevision.

    The caller mutates the lines AFTER this call; the snapshot captures
    the pre-edit state.
    """
    from apps.sales.models import SalesOrderRevision

    if not sales_order.can_revise():
        raise ValueError(f'Cannot revise from status {sales_order.status}')

    last_v = (
        SalesOrderRevision.all_objects
        .filter(sales_order=sales_order)
        .order_by('-version_no').first()
    )
    next_v = (last_v.version_no + 1) if last_v else 1

    snapshot = {
        'header': {
            'code': sales_order.code,
            'status': sales_order.status,
            'customer_id': sales_order.customer_id,
            'order_date': str(sales_order.order_date),
            'requested_delivery_date': str(sales_order.requested_delivery_date or ''),
            'promised_delivery_date': str(sales_order.promised_delivery_date or ''),
            'currency': sales_order.currency,
            'subtotal': str(sales_order.subtotal),
            'tax_total': str(sales_order.tax_total),
            'discount_total': str(sales_order.discount_total),
            'grand_total': str(sales_order.grand_total),
            'notes': sales_order.notes,
        },
        'lines': [
            {
                'line_no': line.line_no,
                'product_id': line.product_id,
                'description': line.description,
                'qty_ordered': str(line.qty_ordered),
                'unit_price': str(line.unit_price),
                'line_discount_pct': str(line.line_discount_pct),
                'line_tax_pct': str(line.line_tax_pct),
                'line_total': str(line.line_total),
                'is_make_to_order': line.is_make_to_order,
            }
            for line in sales_order.lines.all().order_by('line_no')
        ],
    }
    rev = SalesOrderRevision.objects.create(
        tenant=sales_order.tenant,
        sales_order=sales_order,
        version_no=next_v,
        snapshot_json=snapshot,
        revised_by=performed_by,
        reason=reason or '',
    )
    _log(sales_order, 'revise', sales_order.status, sales_order.status,
         performed_by, f'Revision v{next_v}: {reason or "(no reason)"}')
    return rev
