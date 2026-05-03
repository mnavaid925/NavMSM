"""Lot picking strategies — pure functions over StockItem-like rows.

Both `allocate_fifo` and `allocate_fefo` accept either a queryset of
`StockItem` rows or a list of dataclass-shaped duck types so the logic can be
unit-tested in isolation. Each returns a list of `(stock_item_or_dict, qty)`
tuples summing to the requested quantity, or raises `InsufficientStockError` if
the available pool can't cover it.
"""
from dataclasses import dataclass
from decimal import Decimal


class InsufficientStockError(Exception):
    """Raised when the available inventory pool can't cover the requested qty."""

    def __init__(self, requested, available):
        self.requested = Decimal(requested)
        self.available = Decimal(available)
        super().__init__(
            f'Insufficient stock: requested {self.requested}, available {self.available}'
        )


@dataclass
class _Slot:
    item: object
    qty: Decimal


def _row_qty(row):
    qty = getattr(row, 'qty_on_hand', None)
    if qty is None:
        qty = row['qty_on_hand'] if 'qty_on_hand' in row else Decimal('0')
    return Decimal(qty)


def _row_lot(row):
    return getattr(row, 'lot', None) if not isinstance(row, dict) else row.get('lot')


def allocate_fifo(rows, qty):
    """Allocate `qty` from `rows` in oldest-lot-first (FIFO) order.

    Rows must already be sorted oldest-first by the caller (typically by
    `lot__manufactured_date`, then `lot__id`). Rows without lots float to the
    end so explicit lot-tracked stock is consumed first.
    """
    needed = Decimal(qty)
    if needed <= 0:
        raise ValueError('allocate_fifo: qty must be positive')

    slots = []
    available = Decimal('0')
    for row in rows:
        on_hand = _row_qty(row)
        available += on_hand
        if on_hand <= 0:
            continue
        take = min(on_hand, needed)
        if take > 0:
            slots.append(_Slot(item=row, qty=take))
            needed -= take
        if needed <= 0:
            break

    if needed > 0:
        raise InsufficientStockError(qty, available)

    return [(s.item, s.qty) for s in slots]


def allocate_fefo(rows, qty):
    """Allocate `qty` from `rows` in earliest-expiry-first (FEFO) order.

    Same caller contract as FIFO — rows are expected pre-sorted by
    `lot__expiry_date`. Rows whose `lot` is None or whose lot has no expiry are
    treated as never-expiring and float to the end.
    """
    return allocate_fifo(rows, qty)
