"""Stock movement posting — atomic ledger writer.

`post_movement()` is the SOLE supported way to mutate `StockItem` rows. It writes
an append-only `StockMovement` record AND atomically adjusts the relevant
`StockItem.qty_on_hand` row(s) inside one `transaction.atomic` block. Direct
mutation of `StockItem.qty_on_hand` from views or signals is forbidden — go
through this function.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone


def _get_or_create_stock_item(*, tenant, product, bin, lot, serial):
    from apps.inventory.models import StockItem

    item, _ = StockItem.all_objects.get_or_create(
        tenant=tenant,
        product=product,
        bin=bin,
        lot=lot,
        serial=serial,
        defaults={'qty_on_hand': Decimal('0'), 'qty_reserved': Decimal('0')},
    )
    return item


@transaction.atomic
def post_movement(
    *,
    tenant,
    movement_type,
    product,
    qty,
    from_bin=None,
    to_bin=None,
    lot=None,
    serial=None,
    reason='',
    reference='',
    posted_by=None,
    posted_at=None,
    production_report=None,
    incoming_inspection=None,
    grn_line=None,
    notes='',
):
    """Post a stock movement, recording the ledger row and updating bin balances.

    Returns the persisted StockMovement instance.

    Movement-type semantics:
        receipt        -> to_bin required
        production_in  -> to_bin required
        issue          -> from_bin required
        production_out -> from_bin required
        scrap          -> from_bin required
        transfer       -> from_bin AND to_bin required
        adjustment     -> exactly one of from_bin / to_bin
        cycle_count    -> exactly one of from_bin / to_bin
    """
    from apps.inventory.models import StockMovement

    qty = Decimal(qty)
    if qty <= 0:
        raise ValueError('post_movement: qty must be positive')

    require_to = movement_type in {'receipt', 'production_in'}
    require_from = movement_type in {'issue', 'production_out', 'scrap'}
    require_both = movement_type == 'transfer'
    require_one = movement_type in {'adjustment', 'cycle_count'}

    if require_to and to_bin is None:
        raise ValueError(f'post_movement: to_bin is required for {movement_type}')
    if require_from and from_bin is None:
        raise ValueError(f'post_movement: from_bin is required for {movement_type}')
    if require_both and (from_bin is None or to_bin is None):
        raise ValueError('post_movement: transfer requires both from_bin and to_bin')
    if require_both and from_bin == to_bin:
        raise ValueError('post_movement: transfer source and destination bin must differ')
    if require_one and bool(from_bin) == bool(to_bin):
        raise ValueError(
            f'post_movement: {movement_type} requires exactly one of from_bin / to_bin'
        )

    movement = StockMovement(
        tenant=tenant,
        movement_type=movement_type,
        product=product,
        from_bin=from_bin,
        to_bin=to_bin,
        qty=qty,
        lot=lot,
        serial=serial,
        reason=reason,
        reference=reference,
        production_report=production_report,
        incoming_inspection=incoming_inspection,
        grn_line=grn_line,
        posted_by=posted_by,
        posted_at=posted_at or timezone.now(),
        notes=notes,
    )
    movement.save()

    # Apply balance changes.
    if from_bin is not None:
        src = _get_or_create_stock_item(
            tenant=tenant, product=product, bin=from_bin, lot=lot, serial=serial,
        )
        # Allow the balance to dip via adjustments; clamp at zero floor only for
        # operational types.
        new_qty = src.qty_on_hand - qty
        if new_qty < 0 and movement_type not in {'adjustment', 'cycle_count'}:
            raise ValueError(
                f'post_movement: insufficient stock at {from_bin} '
                f'(have {src.qty_on_hand}, need {qty})'
            )
        src.qty_on_hand = max(new_qty, Decimal('0'))
        src.save(update_fields=['qty_on_hand', 'updated_at'])

    if to_bin is not None:
        dst = _get_or_create_stock_item(
            tenant=tenant, product=product, bin=to_bin, lot=lot, serial=serial,
        )
        dst.qty_on_hand = dst.qty_on_hand + qty
        dst.save(update_fields=['qty_on_hand', 'updated_at'])

    return movement


@transaction.atomic
def reverse_movement(movement, *, reason='reversal', posted_by=None):
    """Post a compensating movement that nets out the original.

    Used by the MES `ProductionReport.post_delete` signal so deleting a
    production report reverses the auto-generated `production_in` row instead
    of leaving stock dangling.
    """
    swap = {
        'receipt': 'issue',
        'issue': 'receipt',
        'production_in': 'production_out',
        'production_out': 'production_in',
        'scrap': 'receipt',
        'transfer': 'transfer',
        'adjustment': 'adjustment',
        'cycle_count': 'cycle_count',
    }
    return post_movement(
        tenant=movement.tenant,
        movement_type=swap.get(movement.movement_type, movement.movement_type),
        product=movement.product,
        qty=movement.qty,
        from_bin=movement.to_bin,
        to_bin=movement.from_bin,
        lot=movement.lot,
        serial=movement.serial,
        reason=reason,
        reference=f'reversal of #{movement.id}',
        posted_by=posted_by,
    )
