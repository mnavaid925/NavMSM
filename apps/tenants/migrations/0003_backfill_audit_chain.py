"""Backfill SHA-256 hash chain over pre-existing TenantAuditLog rows.

Walks each tenant's audit log in chronological order and computes a
deterministic prev_hash / this_hash for every legacy row, so the verifier
sees an unbroken chain from row 0 forward (FDA 21 CFR Part 11).

Reverse migration zeroes the columns back out — safe because columns are
blank=True default=''.
"""
import hashlib
import json

from django.db import migrations


def _canonical_payload(action, target_type, target_id, meta, timestamp,
                       tenant_id, user_id):
    return {
        'tenant_id': tenant_id,
        'user_id': user_id,
        'action': action,
        'target_type': target_type,
        'target_id': target_id,
        'meta': meta or {},
        'timestamp': timestamp.isoformat() if timestamp else None,
    }


def _chain_hash(payload, prev_hash):
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256((blob + (prev_hash or '')).encode('utf-8')).hexdigest()


def forwards(apps, schema_editor):
    TenantAuditLog = apps.get_model('tenants', 'TenantAuditLog')
    Tenant = apps.get_model('core', 'Tenant')
    for tenant in Tenant.objects.all().iterator():
        prev_hash = ''
        rows = (
            TenantAuditLog.objects
            .filter(tenant=tenant)
            .order_by('timestamp', 'pk')
        )
        for row in rows.iterator():
            payload = _canonical_payload(
                action=row.action, target_type=row.target_type,
                target_id=row.target_id, meta=row.meta,
                timestamp=row.timestamp, tenant_id=row.tenant_id,
                user_id=row.user_id,
            )
            row.prev_hash = prev_hash
            row.this_hash = _chain_hash(payload, prev_hash)
            row.save(update_fields=['prev_hash', 'this_hash'])
            prev_hash = row.this_hash


def backwards(apps, schema_editor):
    TenantAuditLog = apps.get_model('tenants', 'TenantAuditLog')
    TenantAuditLog.objects.all().update(prev_hash='', this_hash='')


class Migration(migrations.Migration):
    dependencies = [
        ('tenants', '0002_tenantauditlog_prev_hash_tenantauditlog_this_hash'),
        ('core', '0001_initial'),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
