"""C.8 — `Tenant.require_compliance_e_signature` gates a ProductComplianceSignature
on every transition INTO `status='compliant'` (FDA 21 CFR Part 11)."""
import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.plm.models import (
    ComplianceAuditLog, ProductCompliance, ProductComplianceSignature,
)
from apps.plm.tests.factories import make_compliance, make_standard


def _enable_e_sig(tenant):
    tenant.require_compliance_e_signature = True
    tenant.save(update_fields=['require_compliance_e_signature'])


@pytest.mark.django_db
class TestProductComplianceSignatureModel:
    def test_create_signature(self, acme, product, acme_admin):
        rec = make_compliance(tenant=acme, product=product, standard=make_standard())
        sig = ProductComplianceSignature.objects.create(
            tenant=acme, compliance=rec, signer=acme_admin,
            typed_name='Acme Admin', role='QA Manager', reason='initial_certification',
        )
        assert sig.pk is not None
        assert rec.signatures.count() == 1

    def test_signature_immutable_save(self, acme, product, acme_admin):
        rec = make_compliance(tenant=acme, product=product, standard=make_standard())
        sig = ProductComplianceSignature.objects.create(
            tenant=acme, compliance=rec, signer=acme_admin,
            typed_name='Acme Admin', role='QA', reason='initial_certification',
        )
        sig.typed_name = 'Forged Name'
        with pytest.raises(PermissionDenied):
            sig.save()

    def test_signature_immutable_delete(self, acme, product, acme_admin):
        rec = make_compliance(tenant=acme, product=product, standard=make_standard())
        sig = ProductComplianceSignature.objects.create(
            tenant=acme, compliance=rec, signer=acme_admin,
            typed_name='X', reason='initial_certification',
        )
        with pytest.raises(PermissionDenied):
            sig.delete()


@pytest.mark.django_db
class TestE_SignatureRequiredOnTransition:

    def test_create_into_compliant_blocked_without_typed_name(self, client_acme, acme, product):
        _enable_e_sig(acme)
        std = make_standard()
        r = client_acme.post(reverse('plm:compliance_create'), {
            'product': product.pk, 'standard': std.pk, 'status': 'compliant',
            'certification_number': 'C1', 'issuing_body': 'TUV',
            'esig_typed_name': '',  # missing
        })
        assert r.status_code == 200, 'form must re-render with errors'
        assert b'Electronic signature is required' in r.content
        assert ProductCompliance.objects.filter(tenant=acme).count() == 0

    def test_create_into_compliant_succeeds_with_signature(self, client_acme, acme, product):
        _enable_e_sig(acme)
        std = make_standard()
        r = client_acme.post(reverse('plm:compliance_create'), {
            'product': product.pk, 'standard': std.pk, 'status': 'compliant',
            'certification_number': 'C1', 'issuing_body': 'TUV',
            'esig_typed_name': 'Jane Doe', 'esig_role': 'QA Director',
            'esig_reason': 'initial_certification',
        })
        assert r.status_code == 302
        rec = ProductCompliance.objects.get(tenant=acme)
        sigs = rec.signatures.all()
        assert sigs.count() == 1
        sig = sigs.first()
        assert sig.typed_name == 'Jane Doe'
        assert sig.role == 'QA Director'

    def test_create_into_pending_does_not_require_signature(self, client_acme, acme, product):
        _enable_e_sig(acme)
        std = make_standard()
        r = client_acme.post(reverse('plm:compliance_create'), {
            'product': product.pk, 'standard': std.pk, 'status': 'pending',
            'certification_number': 'C1', 'issuing_body': 'TUV',
        })
        assert r.status_code == 302
        assert ProductCompliance.objects.filter(tenant=acme).count() == 1

    def test_edit_pending_to_compliant_requires_signature(self, client_acme, acme, product):
        _enable_e_sig(acme)
        std = make_standard()
        rec = make_compliance(
            tenant=acme, product=product, standard=std, status='pending',
        )
        r = client_acme.post(reverse('plm:compliance_edit', args=[rec.pk]), {
            'product': product.pk, 'standard': std.pk, 'status': 'compliant',
            'certification_number': rec.certification_number,
            'issuing_body': rec.issuing_body,
        })
        assert r.status_code == 200
        rec.refresh_from_db()
        assert rec.status == 'pending', 'transition must be blocked without signature'

    def test_edit_compliant_no_status_change_skips_signature(self, client_acme, acme, product):
        """Editing notes on an already-compliant record must NOT require a new signature."""
        _enable_e_sig(acme)
        std = make_standard()
        rec = make_compliance(
            tenant=acme, product=product, standard=std, status='compliant',
        )
        r = client_acme.post(reverse('plm:compliance_edit', args=[rec.pk]), {
            'product': product.pk, 'standard': std.pk, 'status': 'compliant',
            'certification_number': rec.certification_number,
            'issuing_body': rec.issuing_body, 'notes': 'updated notes',
        })
        assert r.status_code == 302
        rec.refresh_from_db()
        assert rec.notes == 'updated notes'
        # No signature row created on a non-transition save
        assert rec.signatures.count() == 0

    def test_signature_writes_audit_chain_entry(self, client_acme, acme, product):
        _enable_e_sig(acme)
        std = make_standard()
        rec = make_compliance(
            tenant=acme, product=product, standard=std, status='pending',
        )
        before = ComplianceAuditLog.all_objects.filter(tenant=acme, compliance=rec).count()
        client_acme.post(reverse('plm:compliance_edit', args=[rec.pk]), {
            'product': product.pk, 'standard': std.pk, 'status': 'compliant',
            'certification_number': rec.certification_number,
            'issuing_body': rec.issuing_body,
            'esig_typed_name': 'Jane Doe', 'esig_reason': 'initial_certification',
        })
        rec.refresh_from_db()
        assert rec.status == 'compliant'
        assert rec.signatures.count() == 1
        # Two new audit entries: status_changed + e_signature note
        after = ComplianceAuditLog.all_objects.filter(tenant=acme, compliance=rec).count()
        assert after == before + 2
        sig_audit = ComplianceAuditLog.all_objects.filter(
            tenant=acme, compliance=rec, event='note_added',
        ).last()
        assert sig_audit.meta.get('kind') == 'e_signature'
        assert sig_audit.meta.get('typed_name') == 'Jane Doe'

    def test_disabled_tenant_does_not_require_signature(self, client_acme, acme, product):
        """Default behaviour preserved: e-sig is opt-in per-tenant."""
        # tenant.require_compliance_e_signature stays False (default)
        std = make_standard()
        r = client_acme.post(reverse('plm:compliance_create'), {
            'product': product.pk, 'standard': std.pk, 'status': 'compliant',
            'certification_number': 'C1', 'issuing_body': 'TUV',
        })
        assert r.status_code == 302
        rec = ProductCompliance.objects.get(tenant=acme)
        assert rec.signatures.count() == 0
