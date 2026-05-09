"""SHA-256 per-row hash chain for tamper-evident audit logs.

Used by both `tenants.TenantAuditLog` and `plm.ComplianceAuditLog` to satisfy
FDA 21 CFR Part 11 / ISO 9001 audit-trail data-integrity requirements.

Contract:
    For every audit row write:
      this_hash = sha256(canonical_payload || prev_hash).hexdigest()

    Where:
      - canonical_payload = JSON-serialized {tenant_id, action_or_event, target_*,
        meta, timestamp_iso, user_or_performed_by_id} with sorted keys.
      - prev_hash = the latest in-tenant row's `this_hash`, or '' for the
        first row in the tenant.

Verification scans rows in chronological order and recomputes each hash,
re-asserting prev_hash continuity. Any mismatch is reported as the offending
pk + the expected vs actual digest.

Models that opt in must:
  1. Define `prev_hash` and `this_hash` CharField(max_length=64).
  2. Implement `_canonical_payload(self) -> dict` returning the dict to hash.
  3. Identify the per-tenant ordering field (`timestamp` for TenantAuditLog,
     `performed_at` for ComplianceAuditLog).
  4. Call `apply_hash_chain(self, ordering_field)` from `save()` BEFORE the
     row is inserted. Subsequent saves (which would tamper) are blocked
     elsewhere by the model's append-only override.
"""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db import models


def compute_hash(canonical_payload: dict, prev_hash: str) -> str:
    """Deterministic SHA-256 over JSON-canonicalized payload + prev_hash.

    Sorting keys + default=str handles datetimes / Decimals / UUIDs without
    losing fidelity. The same `canonical_payload` always produces the same
    digest, so verification can rerun against on-disk data.
    """
    blob = json.dumps(canonical_payload, sort_keys=True, default=str)
    return hashlib.sha256((blob + (prev_hash or '')).encode('utf-8')).hexdigest()


def apply_hash_chain(instance, ordering_field: str) -> None:
    """Mutate `instance` in place: set `prev_hash` to the latest in-tenant row's
    `this_hash`, then compute `this_hash`. Caller must save afterwards.

    First row in a tenant: `prev_hash = ''`. Idempotent on already-hashed rows
    that are about to be persisted (won't re-chain on second call before save).
    Uses `all_objects` so the query is not constrained by tenant auto-scoping
    middleware (matters when called from a management command without a
    request context).
    """
    if instance.this_hash:
        # Already chained — caller is racing or recomputing; do not re-chain.
        return
    cls = type(instance)
    last = (
        cls.all_objects
        .filter(tenant_id=instance.tenant_id)
        .order_by('-' + ordering_field, '-pk')
        .values_list('this_hash', flat=True)
        .first()
    )
    instance.prev_hash = last or ''
    payload = instance._canonical_payload()
    instance.this_hash = compute_hash(payload, instance.prev_hash)


def verify_chain(model, *, tenant, ordering_field: str) -> dict:
    """Walk every row in tenant order; recompute each hash; report breakage.

    Returns a dict:
        {
          'tenant_id': <id>,
          'rows_checked': <int>,
          'broken': [
            {'pk': <int>, 'reason': 'prev_hash_mismatch'|'this_hash_mismatch',
             'expected': <hex>, 'actual': <hex>},
            ...
          ],
          'ok': <bool>,
        }

    Use `model.all_objects` so cross-tenant verification works without thread-
    local state, and so an immutable QuerySet (which both models use) does not
    raise on the read.
    """
    qs = (
        model.all_objects
        .filter(tenant=tenant)
        .order_by(ordering_field, 'pk')
    )
    broken = []
    expected_prev = ''
    rows_checked = 0
    for row in qs.iterator():
        rows_checked += 1
        if row.prev_hash != expected_prev:
            broken.append({
                'pk': row.pk,
                'reason': 'prev_hash_mismatch',
                'expected': expected_prev,
                'actual': row.prev_hash,
            })
        recomputed = compute_hash(row._canonical_payload(), row.prev_hash)
        if row.this_hash != recomputed:
            broken.append({
                'pk': row.pk,
                'reason': 'this_hash_mismatch',
                'expected': recomputed,
                'actual': row.this_hash,
            })
        # Continue chain from what's actually stored even on mismatch — this
        # surfaces every break point rather than cascading the first error.
        expected_prev = row.this_hash
    return {
        'tenant_id': tenant.pk,
        'rows_checked': rows_checked,
        'broken': broken,
        'ok': not broken,
    }
