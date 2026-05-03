"""Goods Receipt & Putaway helpers — pure-ish functions.

The receipt flow:
    1. operator creates a `GoodsReceiptNote` with one or more `GRNLine` rows
    2. operator marks the GRN as `received` -> we generate one `PutawayTask`
       per GRN line with a suggested bin from the strategy
    3. operator (or admin) confirms each putaway -> `post_movement(receipt, ...)`
       runs and the task flips to `completed`
"""
from decimal import Decimal


def suggest_bin(grn_line, strategy='nearest_empty'):
    """Return a `StorageBin` instance for the given line under the named strategy.

    Strategies:
        fixed_bin     — first non-blocked bin in the destination zone
        nearest_empty — bin in the zone with no current StockItem rows
        abc_zone      — bin matching the product's category code (mocked: any bin)
        directed      — manual placement (returns None; user picks)
    """
    from apps.inventory.models import StockItem, StorageBin

    if strategy == 'directed':
        return None

    bins = StorageBin.objects.filter(
        zone=grn_line.receiving_zone, is_blocked=False,
    ).order_by('code')

    if strategy == 'fixed_bin':
        return bins.first()

    if strategy == 'nearest_empty':
        for b in bins:
            if not StockItem.objects.filter(bin=b).exists():
                return b
        return bins.first()

    if strategy == 'abc_zone':
        # v1: match by ABC class on the bin (set by cycle counts)
        for b in bins:
            if b.abc_class:
                return b
        return bins.first()

    return bins.first()


def generate_putaway_tasks(grn, strategy='nearest_empty'):
    """Create one `PutawayTask` per GRN line. Idempotent — skips lines that
    already have a task. Returns the list of created tasks."""
    from apps.inventory.models import PutawayTask

    created = []
    for line in grn.lines.all():
        if line.putaway_tasks.exists():
            continue
        task = PutawayTask.all_objects.create(
            tenant=grn.tenant,
            grn_line=line,
            suggested_bin=suggest_bin(line, strategy),
            qty=line.received_qty or line.expected_qty or Decimal('0'),
            strategy=strategy,
        )
        created.append(task)
    return created
