"""Available-to-Promise (ATP) service - 17.3.

Pure read. Returns a dataclass; the caller is responsible for persisting
the result as an ATPCalculation row if desired.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class ATPResult:
    requested_qty: Decimal
    requested_date: date
    available_qty: Decimal
    available_date: Optional[date]
    result_status: str       # 'fully_promised' | 'partially_promised' | 'no_stock'
    method: str
    breakdown: dict = field(default_factory=dict)


def _sum_stock(tenant, product, warehouse=None) -> Decimal:
    from django.db.models import Sum
    try:
        from apps.inventory.models import StockItem
    except Exception:
        return Decimal('0')
    qs = StockItem.all_objects.filter(tenant=tenant, product=product)
    if warehouse is not None:
        qs = qs.filter(bin__zone__warehouse=warehouse)
    return qs.aggregate(s=Sum('qty_on_hand'))['s'] or Decimal('0')


def _committed_qty(tenant, product) -> Decimal:
    """Sum of qty_ordered - qty_shipped on confirmed/in-progress SO lines."""
    from django.db.models import Sum, F
    from apps.sales.models import SalesOrderLine
    open_states = ('confirmed', 'in_production', 'fulfilled')
    qs = SalesOrderLine.all_objects.filter(
        tenant=tenant, product=product,
        sales_order__status__in=open_states,
    )
    agg = qs.aggregate(
        committed=Sum(F('qty_ordered') - F('qty_shipped')),
    )
    return agg['committed'] or Decimal('0')


def _open_po_arrivals(tenant, product, on_or_before: date) -> Decimal:
    """Sum of open PO line quantities expected on or before `on_or_before`."""
    from django.db.models import Sum, Q
    try:
        from apps.procurement.models import PurchaseOrderLine
    except Exception:
        return Decimal('0')
    open_po_states = ('approved', 'acknowledged', 'in_progress')
    qs = PurchaseOrderLine.all_objects.filter(
        tenant=tenant, product=product,
        po__status__in=open_po_states,
    ).filter(Q(required_date__isnull=True) | Q(required_date__lte=on_or_before))
    return qs.aggregate(s=Sum('quantity'))['s'] or Decimal('0')


def compute_atp(
    tenant,
    product,
    requested_qty,
    requested_date: date,
    *,
    warehouse=None,
    method: str = 'stock_plus_open_po',
) -> ATPResult:
    """Walk the ATP tiers and return an `ATPResult` snapshot."""
    requested_qty = Decimal(requested_qty)
    on_hand = _sum_stock(tenant, product, warehouse)
    committed = _committed_qty(tenant, product)
    available_now = max(on_hand - committed, Decimal('0'))

    if method == 'stock_only':
        available = available_now
        po_arrivals = Decimal('0')
    elif method in ('stock_plus_open_po', 'stock_plus_pps'):
        po_arrivals = _open_po_arrivals(tenant, product, requested_date)
        available = available_now + po_arrivals
    else:
        available = available_now
        po_arrivals = Decimal('0')

    if available >= requested_qty:
        status = 'fully_promised'
        available_date = requested_date
    elif available > Decimal('0'):
        status = 'partially_promised'
        available_date = requested_date
    else:
        status = 'no_stock'
        available_date = None

    return ATPResult(
        requested_qty=requested_qty,
        requested_date=requested_date,
        available_qty=available,
        available_date=available_date,
        result_status=status,
        method=method,
        breakdown={
            'on_hand': str(on_hand),
            'committed_open_so': str(committed),
            'available_now': str(available_now),
            'open_po_arrivals_by_date': str(po_arrivals),
            'warehouse_id': getattr(warehouse, 'id', None),
        },
    )
