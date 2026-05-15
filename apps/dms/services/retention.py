"""Retention policy helpers for `dms.Document` / `dms.DocumentArchive`.

Pure functions: no ORM imports at module scope to keep this importable
from migrations and unit tests in isolation.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional


def compute_retention_until(effective_date: Optional[date], retention_years: int) -> Optional[date]:
    """Given an effective date + retention years, return the retention-until date.

    Month-end clamped (Feb 29 + N years -> Feb 28 or 29 of the target year).
    Returns None if `effective_date` is None.
    """
    if effective_date is None:
        return None
    if retention_years is None or retention_years <= 0:
        return effective_date
    year = effective_date.year + retention_years
    month = effective_date.month
    day = effective_date.day
    # Month-end clamp for leap day -> non-leap year.
    while True:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1
            if day <= 0:
                return effective_date


def is_due_for_archive(document, today: Optional[date] = None) -> bool:
    """Return True if the document is past its retention window AND not on hold."""
    today = today or date.today()
    if document.retention_until is None or document.is_locked or document.status == 'archived':
        return False
    return document.retention_until < today


def days_until_retention(document, today: Optional[date] = None) -> Optional[int]:
    """Return days remaining until retention_until, or None if unbounded."""
    if document.retention_until is None:
        return None
    today = today or date.today()
    return (document.retention_until - today).days
