"""Shipment workflow service (17.4).

Race-safe state transitions. Confirming delivery is signal-driven -
this service just flips the status; the post_save signal in
apps/sales/signals.py emits the StockMovement rows.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone


def _conditional_update(shipment, *, from_status, to_status, **extras):
    from apps.sales.models import Shipment
    extras['status'] = to_status
    extras['updated_at'] = timezone.now()
    rows = (
        Shipment.all_objects
        .filter(pk=shipment.pk, status=from_status)
        .update(**extras)
    )
    if rows:
        shipment.refresh_from_db()
    return bool(rows)


@transaction.atomic
def pick_shipment(shipment, performed_by=None):
    if not shipment.can_pick():
        raise ValueError(f'Cannot pick from {shipment.status}')
    if not _conditional_update(shipment, from_status='planned', to_status='picked'):
        raise ValueError('Concurrent update detected; please refresh.')
    shipment.shipment_lines.all().update(pick_status='picked')


@transaction.atomic
def pack_shipment(shipment, performed_by=None):
    if not shipment.can_pack():
        raise ValueError(f'Cannot pack from {shipment.status}')
    if not _conditional_update(shipment, from_status='picked', to_status='packed'):
        raise ValueError('Concurrent update detected; please refresh.')
    shipment.shipment_lines.all().update(pick_status='packed')


@transaction.atomic
def dispatch_shipment(shipment, performed_by=None):
    if not shipment.can_dispatch():
        raise ValueError(f'Cannot dispatch from {shipment.status}')
    if not _conditional_update(
        shipment, from_status='packed', to_status='in_transit',
        actual_ship_date=timezone.now().date(),
    ):
        raise ValueError('Concurrent update detected; please refresh.')


@transaction.atomic
def confirm_delivery(shipment, performed_by=None):
    """in_transit -> delivered. Signal auto-emits StockMovement rows."""
    if not shipment.can_deliver():
        raise ValueError(f'Cannot mark delivered from {shipment.status}')
    if not _conditional_update(
        shipment, from_status='in_transit', to_status='delivered',
        actual_delivery_date=timezone.now().date(),
    ):
        raise ValueError('Concurrent update detected; please refresh.')

    # Mark linked SalesOrderLine.qty_shipped denorms
    from django.db.models import F
    from apps.sales.models import SalesOrderLine
    for line in shipment.shipment_lines.all():
        SalesOrderLine.all_objects.filter(pk=line.order_line_id).update(
            qty_shipped=F('qty_shipped') + (line.qty_shipped or line.qty_to_ship),
        )


@transaction.atomic
def cancel_shipment(shipment, performed_by=None):
    if not shipment.can_cancel():
        raise ValueError(f'Cannot cancel from {shipment.status}')
    prev = shipment.status
    if not _conditional_update(shipment, from_status=prev, to_status='cancelled'):
        raise ValueError('Concurrent update detected; please refresh.')
