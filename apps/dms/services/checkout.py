"""Check-in / check-out service for `dms.DocumentVersion`.

Implements an application-level optimistic lock: a version is "checked
out" when `checked_out_by` is set; only that user (or a tenant admin)
can release it. Concurrent races are mitigated by a conditional
`UPDATE ... WHERE checked_out_by IS NULL` rather than a SELECT-then-UPDATE.

This is NOT a DB-level lock - if two requests collide in the same
millisecond, only one wins, but the loser does not corrupt state.
"""
from __future__ import annotations

from typing import Optional

from django.utils import timezone


class CheckoutError(Exception):
    """Raised when a check-in / check-out operation cannot proceed."""


def is_checked_out(version) -> bool:
    return bool(version.checked_out_by_id) and version.checked_out_at is not None


def check_out(version, user) -> None:
    """Mark `version` as checked out by `user`.

    Uses conditional UPDATE so two simultaneous requests cannot both win.
    Raises CheckoutError if the row is already held by someone else.
    """
    from apps.dms.models import DocumentVersion

    updated = (
        DocumentVersion.all_objects
        .filter(pk=version.pk, checked_out_by__isnull=True)
        .update(checked_out_by=user, checked_out_at=timezone.now())
    )
    if updated != 1:
        # Refresh to expose who holds it.
        version.refresh_from_db(fields=['checked_out_by', 'checked_out_at'])
        if version.checked_out_by_id == user.id:
            return  # already ours - no-op
        raise CheckoutError(
            f'Document version is already checked out by '
            f'{version.checked_out_by} since {version.checked_out_at:%Y-%m-%d %H:%M}.'
        )
    version.checked_out_by = user
    version.checked_out_at = timezone.now()


def check_in(version, user, *, is_admin: bool = False) -> None:
    """Release the lock on `version`.

    Only the holder (or a tenant admin) may check in.
    """
    if not is_checked_out(version):
        return
    if version.checked_out_by_id != user.id and not is_admin:
        raise CheckoutError(
            'Only the user who checked the document out (or a tenant admin) '
            'may check it back in.'
        )
    from apps.dms.models import DocumentVersion
    DocumentVersion.all_objects.filter(pk=version.pk).update(
        checked_out_by=None, checked_out_at=None,
    )
    version.checked_out_by = None
    version.checked_out_at = None


def holder(version) -> Optional[object]:
    """Return the User currently holding the lock, or None."""
    return version.checked_out_by if is_checked_out(version) else None
