"""SHA-256 hash-chain regression for TenantAuditLog (FDA 21 CFR Part 11)."""
import pytest

from apps.core.models import Tenant, set_current_tenant
from apps.core.services.audit_chain import compute_hash
from apps.tenants.models import TenantAuditLog
from apps.tenants.services.audit_chain import verify_tenant_audit_chain


@pytest.fixture
def acme(db):
    t = Tenant.objects.create(name='Acme', slug='acme-chain', is_active=True)
    set_current_tenant(t)
    yield t
    set_current_tenant(None)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex', slug='globex-chain', is_active=True)


@pytest.mark.django_db
class TestTenantAuditLogChain:

    def test_first_row_has_empty_prev_hash(self, acme):
        row = TenantAuditLog.objects.create(tenant=acme, action='first.event')
        assert row.prev_hash == ''
        assert row.this_hash != ''
        assert len(row.this_hash) == 64

    def test_subsequent_rows_chain_from_previous(self, acme):
        r1 = TenantAuditLog.objects.create(tenant=acme, action='r1')
        r2 = TenantAuditLog.objects.create(tenant=acme, action='r2')
        r3 = TenantAuditLog.objects.create(tenant=acme, action='r3')
        assert r2.prev_hash == r1.this_hash
        assert r3.prev_hash == r2.this_hash
        # Each digest is unique
        assert len({r1.this_hash, r2.this_hash, r3.this_hash}) == 3

    def test_chain_isolated_per_tenant(self, acme, globex):
        TenantAuditLog.objects.create(tenant=acme, action='acme1')
        # Switching tenant context isolates the chain
        g_row = TenantAuditLog.objects.create(tenant=globex, action='globex1')
        # globex's first row has empty prev_hash even though acme has a row
        assert g_row.prev_hash == ''

    def test_verify_chain_clean(self, acme):
        for i in range(5):
            TenantAuditLog.objects.create(tenant=acme, action=f'evt-{i}')
        result = verify_tenant_audit_chain(acme)
        assert result['ok'] is True
        assert result['rows_checked'] == 5
        assert result['broken'] == []

    def test_verify_chain_detects_tampered_meta(self, acme):
        """Mutate `meta` directly via raw SQL so the model's immutable save()
        guard does not block the test, then confirm verify_chain reports the
        tampered row."""
        for i in range(3):
            TenantAuditLog.objects.create(tenant=acme, action=f'evt-{i}', meta={'i': i})
        target = TenantAuditLog.objects.filter(tenant=acme, action='evt-1').first()
        # Bypass the model save by going through raw SQL
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE tenants_tenantauditlog SET meta=%s WHERE id=%s",
                ['{"tampered": true}', target.pk],
            )
        result = verify_tenant_audit_chain(acme)
        assert result['ok'] is False
        # The tampered row's recomputed this_hash will not match what's stored
        broken_pks = {b['pk'] for b in result['broken']}
        assert target.pk in broken_pks
        # Reasons surface as this_hash_mismatch on the tampered row, then
        # prev_hash_mismatch on the next row (chain cascades)
        reasons = {b['reason'] for b in result['broken']}
        assert 'this_hash_mismatch' in reasons

    def test_compute_hash_deterministic(self):
        payload = {'a': 1, 'b': 'two', 'c': None}
        h1 = compute_hash(payload, 'prev')
        h2 = compute_hash(payload, 'prev')
        assert h1 == h2
        # Same payload, different prev hash -> different output
        assert compute_hash(payload, 'other') != h1
        # Hex digest of correct length
        assert len(h1) == 64

    def test_chain_survives_natural_save_path(self, acme):
        """End-to-end: write rows the way real signal handlers do (via
        objects.create), then verify."""
        for i in range(10):
            TenantAuditLog.objects.create(
                tenant=acme, action=f'natural-{i}',
                target_type='Smoke', target_id=str(i), meta={'k': i},
            )
        assert verify_tenant_audit_chain(acme)['ok'] is True
