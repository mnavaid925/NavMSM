"""View-layer integration: CRUD, signal-emitted audit, list filters, D-CR-07 banner."""
from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.plm.models import ComplianceAuditLog, Product, ProductCompliance
from apps.plm.tests.factories import make_compliance, make_standard


@pytest.mark.django_db
class TestComplianceCRUD:
    def test_create_emits_audit(self, client_acme, acme, product):
        std = make_standard()
        r = client_acme.post(reverse('plm:compliance_create'), {
            'product': product.pk, 'standard': std.pk, 'status': 'compliant',
            'certification_number': 'CRT-001', 'issuing_body': 'TUV',
            'notes': '',
        })
        assert r.status_code == 302
        rec = ProductCompliance.objects.get(tenant=acme, certification_number='CRT-001')
        assert ComplianceAuditLog.objects.filter(compliance=rec, event='created').exists()

    def test_status_change_emits_audit(self, client_acme, acme, product):
        std = make_standard()
        rec = make_compliance(tenant=acme, product=product, standard=std, status='pending')
        before = ComplianceAuditLog.objects.filter(compliance=rec).count()
        r = client_acme.post(reverse('plm:compliance_edit', args=[rec.pk]), {
            'product': product.pk, 'standard': std.pk, 'status': 'compliant',
            'certification_number': rec.certification_number,
            'issuing_body': rec.issuing_body, 'notes': '',
        })
        assert r.status_code == 302, r.content
        rec.refresh_from_db()
        assert rec.status == 'compliant'
        after = ComplianceAuditLog.objects.filter(compliance=rec).count()
        assert after == before + 1
        new_entry = ComplianceAuditLog.objects.filter(compliance=rec, event='status_changed').last()
        assert new_entry.meta == {'from': 'pending', 'to': 'compliant'}

    def test_edit_notes_only_no_audit(self, client_acme, acme, product):
        std = make_standard()
        rec = make_compliance(tenant=acme, product=product, standard=std, status='compliant')
        before = ComplianceAuditLog.objects.filter(compliance=rec).count()
        r = client_acme.post(reverse('plm:compliance_edit', args=[rec.pk]), {
            'product': product.pk, 'standard': std.pk, 'status': rec.status,
            'certification_number': rec.certification_number,
            'issuing_body': rec.issuing_body, 'notes': 'updated',
        })
        assert r.status_code == 302, r.content
        after = ComplianceAuditLog.objects.filter(compliance=rec).count()
        assert after == before  # no status change -> no new audit row

    def test_delete_cascades_audit(self, client_acme, acme, product):
        """Parent CASCADE removes audit children — that's record lifecycle, not tampering."""
        std = make_standard()
        rec = make_compliance(tenant=acme, product=product, standard=std)
        rec_pk = rec.pk
        r = client_acme.post(reverse('plm:compliance_delete', args=[rec_pk]))
        assert r.status_code == 302
        assert not ProductCompliance.objects.filter(pk=rec_pk).exists()
        assert ComplianceAuditLog.all_objects.filter(compliance_id=rec_pk).count() == 0


@pytest.mark.django_db
class TestComplianceListFilters:
    def test_list_renders(self, client_acme, acme, product):
        make_compliance(tenant=acme, product=product, standard=make_standard())
        r = client_acme.get(reverse('plm:compliance_list'))
        assert r.status_code == 200

    def test_search_by_cert_number(self, client_acme, acme, product):
        make_compliance(tenant=acme, product=product, standard=make_standard(),
                        certification_number='UNIQUEFOO')
        r = client_acme.get(reverse('plm:compliance_list'), {'q': 'UNIQUEFOO'})
        assert b'UNIQUEFOO' in r.content


@pytest.mark.django_db
class TestExpiringSoonBannerD07:
    """D-CR-07 regression: banner counts compliant records only."""

    def test_banner_excludes_non_compliant(self, client_acme, acme, category):
        soon = date.today() + timedelta(days=14)
        for i, status in enumerate(['compliant', 'compliant', 'compliant',
                                     'non_compliant', 'expired']):
            p = Product.objects.create(
                tenant=acme, sku=f'EXP-{i}', name=f'P{i}', category=category,
                product_type='component', status='active',
            )
            make_compliance(
                tenant=acme, product=p, standard=make_standard(),
                status=status, expiry_date=soon,
            )
        r = client_acme.get(reverse('plm:compliance_list'))
        # After D-CR-07 fix the count must be 3, not 5
        assert r.context['expiring_soon_count'] == 3

    def test_banner_zero_when_outside_window(self, client_acme, acme, product):
        far = date.today() + timedelta(days=60)
        make_compliance(tenant=acme, product=product, standard=make_standard(),
                        status='compliant', expiry_date=far)
        r = client_acme.get(reverse('plm:compliance_list'))
        assert r.context['expiring_soon_count'] == 0
