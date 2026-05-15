"""Supplier-chargeback helpers for Module 18 - Returns & RMA (analytics).

Thin workflow helpers around `SupplierChargeback`. The status enum is
`draft -> pending -> issued -> disputed -> recovered | written_off`;
these functions guard the legal transitions so a hand-crafted POST can
never jump straight from draft to recovered.
"""
from __future__ import annotations

from django.utils import timezone

# Allowed forward transitions per current status.
_TRANSITIONS = {
    'draft': {'pending'},
    'pending': {'issued'},
    'issued': {'disputed', 'recovered', 'written_off'},
    'disputed': {'recovered', 'written_off'},
    'recovered': set(),
    'written_off': set(),
}


def can_transition(chargeback, to_status: str) -> bool:
    """True when `chargeback` may legally move to `to_status`."""
    return to_status in _TRANSITIONS.get(chargeback.status, set())


def apply_transition(chargeback, to_status: str, performed_by=None) -> None:
    """Move `chargeback` to `to_status`, stamping the matching date denorm.

    Raises ValueError on an illegal transition so the calling view can
    surface a `messages.error`.
    """
    if not can_transition(chargeback, to_status):
        raise ValueError(
            f'Cannot move chargeback from {chargeback.status} to {to_status}.',
        )
    chargeback.status = to_status
    today = timezone.now().date()
    if to_status == 'issued' and not chargeback.issued_date:
        chargeback.issued_date = today
    if to_status == 'recovered' and not chargeback.recovered_date:
        chargeback.recovered_date = today
    chargeback.save(update_fields=[
        'status', 'issued_date', 'recovered_date', 'updated_at',
    ])
