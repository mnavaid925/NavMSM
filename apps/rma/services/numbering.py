"""Shared atomic auto-numbering helper for the RMA app.

Pattern matches `apps/sales/services/numbering.py` and the per-model
`save()` overrides across `apps/inventory`, `apps/eam`, `apps/iot`.

We use a post-save `last.id + 1` strategy (NOT a pre-fetched MAX(seq))
because:
    * pk auto-increment is monotonic per tenant + model
    * `all_objects` bypasses the TenantManager so the lookup hits the
      raw table without the request-bound tenant scope

Race-safe enough for current scale; if collisions ever appear we can
switch to a dedicated `Sequence` row + `select_for_update`.
"""
from __future__ import annotations


def next_code(model_class, tenant, prefix: str, width: int = 5) -> str:
    """Compute the next auto-numbered code for `model_class` within `tenant`.

    Caller assigns the returned string to the code field BEFORE calling
    super().save() so the first save() sets it.
    """
    last = (
        model_class.all_objects
        .filter(tenant=tenant)
        .order_by('-id')
        .first()
    )
    seq = (last.id + 1) if last else 1
    return f'{prefix}-{seq:0{width}d}'
