"""Blanket-order consumption helpers.

When a ScheduleRelease moves out of ``draft`` (release / receive), we tally
the per-line consumption back onto the parent BlanketOrderLine (and the
BlanketOrder.consumed_value denorm) so the remaining capacity is always
visible without recomputing on every page load.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import F


@transaction.atomic
def consume_release(release):
    """Apply a release's line quantities to its blanket order's consumption denorms.

    Idempotent at the line-level via the release.status guard - callers must
    only invoke this on the draft -> released transition. Re-running on an
    already-released release would double-count.
    """
    from apps.procurement.models import BlanketOrder, BlanketOrderLine

    if release.status != 'released':
        raise ValueError('consume_release: release must be in "released" state.')

    blanket = release.blanket_order
    total_increment = Decimal('0')

    for line in release.lines.select_related('blanket_order_line').all():
        bol = line.blanket_order_line
        # Use a conditional UPDATE so concurrent releases can't overdraw.
        rows = BlanketOrderLine.all_objects.filter(
            pk=bol.pk,
            consumed_quantity__lte=F('total_quantity') - line.quantity,
        ).update(consumed_quantity=F('consumed_quantity') + line.quantity)
        if rows == 0:
            raise ValueError(
                f'Release line for {bol} would exceed blanket commitment.'
            )
        total_increment += line.line_total

    BlanketOrder.all_objects.filter(pk=blanket.pk).update(
        consumed_value=F('consumed_value') + total_increment,
    )


@transaction.atomic
def reverse_release(release):
    """Reverse a release's consumption (used when cancelling a released release)."""
    from apps.procurement.models import BlanketOrder, BlanketOrderLine

    blanket = release.blanket_order
    total_decrement = Decimal('0')

    for line in release.lines.select_related('blanket_order_line').all():
        BlanketOrderLine.all_objects.filter(pk=line.blanket_order_line_id).update(
            consumed_quantity=F('consumed_quantity') - line.quantity,
        )
        total_decrement += line.line_total

    BlanketOrder.all_objects.filter(pk=blanket.pk).update(
        consumed_value=F('consumed_value') - total_decrement,
    )
