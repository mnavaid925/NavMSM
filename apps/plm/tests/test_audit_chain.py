"""SHA-256 hash-chain regression for plm.ComplianceAuditLog (FDA 21 CFR Part 11)."""
import pytest

from apps.plm.models import ComplianceAuditLog
from apps.plm.services.audit_chain import verify_compliance_audit_chain
from apps.plm.tests.factories import make_compliance, make_standard


@pytest.mark.django_db
class TestComplianceAuditChain:

    def _seed_three_compliance_records_with_audit(self, acme, product):
        """Create 3 ProductCompliance rows, each emitting a `created` audit row."""
        records = []
        for _ in range(3):
            std = make_standard()
            rec = make_compliance(tenant=acme, product=product, standard=std,
                                  status='pending')
            records.append(rec)
        return records

    def test_first_audit_row_has_empty_prev_hash(self, acme, product):
        rec = make_compliance(tenant=acme, product=product, standard=make_standard())
        first_audit = ComplianceAuditLog.all_objects.filter(
            tenant=acme, compliance=rec,
        ).order_by('performed_at', 'pk').first()
        assert first_audit.prev_hash == ''
        assert first_audit.this_hash != ''
        assert len(first_audit.this_hash) == 64

    def test_subsequent_audit_rows_chain(self, acme, product):
        recs = self._seed_three_compliance_records_with_audit(acme, product)
        audits = list(
            ComplianceAuditLog.all_objects.filter(tenant=acme)
            .order_by('performed_at', 'pk')
        )
        assert len(audits) >= 3
        for i in range(1, len(audits)):
            assert audits[i].prev_hash == audits[i - 1].this_hash, (
                f'chain broken at index {i}: prev={audits[i].prev_hash[:16]} '
                f'expected={audits[i-1].this_hash[:16]}'
            )

    def test_chain_isolated_per_tenant(self, acme, globex, product):
        """Globex's audit chain starts fresh even when acme already has rows."""
        std = make_standard()
        make_compliance(tenant=acme, product=product, standard=std)
        # Build a globex product + compliance row
        from apps.plm.models import Product, ProductCategory
        globex_cat = ProductCategory.objects.create(
            tenant=globex, code='C', name='Components',
        )
        globex_prod = Product.objects.create(
            tenant=globex, sku='G-001', name='G product',
            category=globex_cat, product_type='component',
        )
        make_compliance(tenant=globex, product=globex_prod, standard=std)
        first_globex_audit = (
            ComplianceAuditLog.all_objects.filter(tenant=globex)
            .order_by('performed_at', 'pk').first()
        )
        assert first_globex_audit.prev_hash == ''

    def test_verify_chain_clean(self, acme, product):
        self._seed_three_compliance_records_with_audit(acme, product)
        result = verify_compliance_audit_chain(acme)
        assert result['ok'] is True
        assert result['rows_checked'] >= 3
        assert result['broken'] == []

    def test_verify_chain_detects_tampered_meta(self, acme, product):
        recs = self._seed_three_compliance_records_with_audit(acme, product)
        # Mutate one audit row's meta via raw SQL (bypass immutable manager)
        target = ComplianceAuditLog.all_objects.filter(
            tenant=acme, compliance=recs[1],
        ).first()
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE plm_complianceauditlog SET meta=%s WHERE id=%s",
                ['{"tampered": true}', target.pk],
            )
        result = verify_compliance_audit_chain(acme)
        assert result['ok'] is False
        broken_pks = {b['pk'] for b in result['broken']}
        assert target.pk in broken_pks

    def test_status_change_creates_chained_audit(self, acme, product, client_acme):
        """End-to-end: HTTP POST -> view -> signal -> audit row -> chain."""
        from django.urls import reverse
        std = make_standard()
        rec = make_compliance(tenant=acme, product=product, standard=std,
                              status='pending')
        before_chain_len = ComplianceAuditLog.all_objects.filter(tenant=acme).count()
        r = client_acme.post(reverse('plm:compliance_edit', args=[rec.pk]), {
            'product': product.pk, 'standard': std.pk, 'status': 'compliant',
            'certification_number': rec.certification_number,
            'issuing_body': rec.issuing_body, 'notes': '',
        })
        assert r.status_code == 302
        after = ComplianceAuditLog.all_objects.filter(tenant=acme).order_by(
            'performed_at', 'pk',
        )
        assert after.count() == before_chain_len + 1
        # Whole chain still verifies
        assert verify_compliance_audit_chain(acme)['ok'] is True
