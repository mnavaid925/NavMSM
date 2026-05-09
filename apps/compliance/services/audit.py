"""Sub-module 13.3 services - audit-log archival with hash chaining.

The chain digest is a SHA-256 of ``previous_hash || canonical_rows`` —
``canonical_rows`` is a sorted JSON of (action, target_type, target_id,
timestamp, meta). Tampering with any prior archive breaks subsequent
verifications.
"""
import hashlib
import json
from datetime import date

from django.db import transaction

from apps.compliance import models


def _canonical_rows(qs):
    payload = [
        {
            'action': r.action,
            'target_type': r.target_type,
            'target_id': r.target_id,
            'timestamp': r.timestamp.isoformat() if r.timestamp else None,
            'meta': r.meta or {},
        }
        for r in qs.order_by('timestamp', 'pk')
    ]
    return json.dumps(payload, sort_keys=True, default=str).encode('utf-8')


@transaction.atomic
def archive_period(tenant, *, period_start: date, period_end: date, by=None):
    """Snapshot tenant.TenantAuditLog rows for [period_start, period_end] inclusive.

    Idempotent on (tenant, period_start, period_end) — a second call returns
    the existing archive row.
    """
    from apps.tenants.models import TenantAuditLog

    existing = models.AuditLogArchive.all_objects.filter(
        tenant=tenant, period_start=period_start, period_end=period_end,
    ).first()
    if existing is not None:
        return existing

    rows = TenantAuditLog.objects.filter(
        tenant=tenant,
        timestamp__date__gte=period_start,
        timestamp__date__lte=period_end,
    )
    canonical = _canonical_rows(rows)

    previous = (
        models.AuditLogArchive.all_objects
        .filter(tenant=tenant)
        .exclude(period_end__gt=period_end)
        .order_by('-period_end')
        .first()
    )
    prev_hash = previous.hash_chain if previous else ''
    digest = hashlib.sha256(prev_hash.encode('utf-8') + canonical).hexdigest()

    return models.AuditLogArchive.objects.create(
        tenant=tenant,
        period_start=period_start,
        period_end=period_end,
        record_count=rows.count(),
        hash_chain=digest,
        previous_archive=previous,
        generated_by=by,
    )


def verify_chain(tenant) -> dict:
    """Walk the archive chain in date order; return a verification report.

    Returns a dict::

        {'ok': bool, 'broken_at': <archive_number or None>, 'count': int}

    A break means the digest stored on archive N does NOT match
    ``sha256(prev_hash || canonical_rows)`` recomputed from the current DB.
    """
    from apps.tenants.models import TenantAuditLog

    archives = list(
        models.AuditLogArchive.all_objects.filter(tenant=tenant)
        .order_by('period_start')
    )
    prev_hash = ''
    for archive in archives:
        rows = TenantAuditLog.objects.filter(
            tenant=tenant,
            timestamp__date__gte=archive.period_start,
            timestamp__date__lte=archive.period_end,
        )
        canonical = _canonical_rows(rows)
        expected = hashlib.sha256(
            prev_hash.encode('utf-8') + canonical
        ).hexdigest()
        if expected != archive.hash_chain:
            return {
                'ok': False,
                'broken_at': archive.archive_number,
                'count': len(archives),
            }
        prev_hash = archive.hash_chain
    return {'ok': True, 'broken_at': None, 'count': len(archives)}
