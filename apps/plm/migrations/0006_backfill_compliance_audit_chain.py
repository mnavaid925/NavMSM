"""Backfill SHA-256 hash chain over pre-existing ComplianceAuditLog rows.

The model layer overrides `save()` to raise on existing pks, so we drive the
backfill through `update()` per row via the historical model. Historical
models from `apps.get_model()` do NOT inherit the immutable manager / save
override, so this is safe inside the migration even though it would be
forbidden at runtime.
"""
import hashlib
import json

from django.db import migrations


def _canonical_payload(compliance_id, event, performed_by_id, performed_at,
                       meta, tenant_id):
    return {
        'tenant_id': tenant_id,
        'compliance_id': compliance_id,
        'event': event,
        'performed_by_id': performed_by_id,
        'performed_at': performed_at.isoformat() if performed_at else None,
        'meta': meta or {},
    }


def _chain_hash(payload, prev_hash):
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256((blob + (prev_hash or '')).encode('utf-8')).hexdigest()


def forwards(apps, schema_editor):
    ComplianceAuditLog = apps.get_model('plm', 'ComplianceAuditLog')
    Tenant = apps.get_model('core', 'Tenant')
    for tenant in Tenant.objects.all().iterator():
        prev_hash = ''
        rows = (
            ComplianceAuditLog.objects
            .filter(tenant=tenant)
            .order_by('performed_at', 'pk')
        )
        for row in rows.iterator():
            payload = _canonical_payload(
                compliance_id=row.compliance_id, event=row.event,
                performed_by_id=row.performed_by_id,
                performed_at=row.performed_at, meta=row.meta,
                tenant_id=row.tenant_id,
            )
            this_hash = _chain_hash(payload, prev_hash)
            ComplianceAuditLog.objects.filter(pk=row.pk).update(
                prev_hash=prev_hash, this_hash=this_hash,
            )
            prev_hash = this_hash


def backwards(apps, schema_editor):
    ComplianceAuditLog = apps.get_model('plm', 'ComplianceAuditLog')
    ComplianceAuditLog.objects.all().update(prev_hash='', this_hash='')


class Migration(migrations.Migration):
    dependencies = [
        ('plm', '0005_complianceauditlog_prev_hash_and_more'),
        ('core', '0001_initial'),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
