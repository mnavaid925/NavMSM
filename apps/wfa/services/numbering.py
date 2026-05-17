"""Shared atomic auto-numbering helper for the WFA app.

Pattern mirrors `apps/dms/services/numbering.py` and
`apps/rma/services/numbering.py`.

Caller assigns the returned string to the code field BEFORE calling
super().save() so the first save() sets it.
"""
from __future__ import annotations


def next_code(model_class, tenant, prefix: str, width: int = 5) -> str:
    last = (
        model_class.all_objects
        .filter(tenant=tenant)
        .order_by('-id')
        .first()
    )
    seq = (last.id + 1) if last else 1
    return f'{prefix}-{seq:0{width}d}'
