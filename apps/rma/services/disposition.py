"""Disposition routing helpers for Module 18 - Returns & RMA.

A `ReturnReceiptLine.disposition` decides what physically happens to a
returned unit after inspection. `route_disposition` is a pure-function
classifier that says which downstream action the post_save signal in
`apps/rma/signals.py` should take; the signal owns the side effects.
"""
from __future__ import annotations

# disposition value -> downstream action keyword
RESTOCK = 'restock'
REPAIR_TICKET = 'repair_ticket'
SUPPLIER_RETURN = 'supplier_return'
NONE = 'none'

# Dispositions that put usable stock back into inventory.
_RESTOCK_DISPOSITIONS = {'restock'}
# Dispositions that spawn a RepairOrder.
_REPAIR_DISPOSITIONS = {'repair', 'refurbish'}
# Dispositions that flag a supplier return-to-vendor (analytics / chargeback).
_SUPPLIER_DISPOSITIONS = {'return_to_supplier'}


def route_disposition(disposition: str) -> str:
    """Map a raw disposition code to a downstream action keyword."""
    if disposition in _RESTOCK_DISPOSITIONS:
        return RESTOCK
    if disposition in _REPAIR_DISPOSITIONS:
        return REPAIR_TICKET
    if disposition in _SUPPLIER_DISPOSITIONS:
        return SUPPLIER_RETURN
    return NONE
