"""Legal hold helpers - block archive/retention while at least one
active LegalHold references a Document.

When `apply_hold(hold)` runs, every linked Document gets `is_locked=True`.
When `release_hold(hold)` runs, each Document is re-evaluated: if no
other active hold still references it, `is_locked` is cleared.
"""
from __future__ import annotations

from django.db import transaction


def apply_hold(hold) -> None:
    """Mark every document referenced by an active `hold` as locked.

    Idempotent. Safe to call repeatedly.
    """
    if hold.status != 'active':
        return
    docs = list(hold.documents.all())
    if not docs:
        return
    from apps.dms.models import Document
    pks = [d.pk for d in docs]
    with transaction.atomic():
        Document.all_objects.filter(pk__in=pks).update(is_locked=True)


def release_hold(hold) -> None:
    """Clear `is_locked` on documents only if no other active hold covers them."""
    docs = list(hold.documents.all())
    if not docs:
        return
    from apps.dms.models import Document, LegalHold
    with transaction.atomic():
        for doc in docs:
            other_active = (
                LegalHold.all_objects
                .filter(documents=doc, status='active')
                .exclude(pk=hold.pk)
                .exists()
            )
            if not other_active:
                Document.all_objects.filter(pk=doc.pk).update(is_locked=False)


def is_under_hold(document) -> bool:
    """Cheap O(1) wrapper on the denorm."""
    return bool(document.is_locked)
