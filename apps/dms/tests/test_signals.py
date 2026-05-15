"""Cross-module signal handlers: cascades + idempotency."""
from datetime import date

import pytest

from apps.dms.models import (
    Document,
    DocumentApprovalRequest,
    DocumentSignature,
    DocumentVersion,
    LegalHold,
    RetentionPolicy,
)


@pytest.mark.django_db
class TestVersionReleasedCascade:
    def test_release_supersedes_prior(self, tenant_a, document):
        v1 = DocumentVersion.objects.create(
            tenant=tenant_a, document=document, version='1', status='released',
        )
        v2 = DocumentVersion.objects.create(
            tenant=tenant_a, document=document, version='2', status='released',
        )
        v1.refresh_from_db()
        assert v1.status == 'superseded'

    def test_release_updates_current_version(self, tenant_a, document):
        v = DocumentVersion.objects.create(
            tenant=tenant_a, document=document, version='1', status='released',
        )
        document.refresh_from_db()
        assert document.current_version_id == v.id

    def test_release_idempotent(self, tenant_a, document):
        v = DocumentVersion.objects.create(
            tenant=tenant_a, document=document, version='1', status='released',
        )
        v.save()  # second save
        # Nothing should explode; current_version still points at v.
        document.refresh_from_db()
        assert document.current_version_id == v.id


@pytest.mark.django_db
class TestApprovalApprovedCascade:
    def test_approval_flips_document_effective(self, tenant_a, document, workflow_with_stages):
        req = DocumentApprovalRequest.objects.create(
            tenant=tenant_a, document=document, workflow=workflow_with_stages,
            status='approved', effective_date=date.today(),
        )
        document.refresh_from_db()
        assert document.status == 'effective'
        assert document.effective_date == date.today()


@pytest.mark.django_db
class TestLegalHoldM2M:
    def test_add_documents_locks_them(self, tenant_a, document):
        hold = LegalHold.objects.create(tenant=tenant_a, name='X', status='active')
        hold.documents.add(document)
        document.refresh_from_db()
        assert document.is_locked

    def test_remove_only_hold_unlocks(self, tenant_a, document):
        hold = LegalHold.objects.create(tenant=tenant_a, name='X', status='active')
        hold.documents.add(document)
        hold.documents.remove(document)
        document.refresh_from_db()
        assert not document.is_locked


@pytest.mark.django_db
class TestRetentionDenorm:
    def test_doc_save_computes_retention(self, tenant_a, policy):
        d = Document.objects.create(
            tenant=tenant_a, title='T',
            effective_date=date(2025, 1, 1),
            retention_policy=policy,
        )
        d.refresh_from_db()
        assert d.retention_until == date(2030, 1, 1)

    def test_policy_year_change_propagates(self, tenant_a, policy):
        d = Document.objects.create(
            tenant=tenant_a, title='T',
            effective_date=date(2025, 1, 1),
            retention_policy=policy,
        )
        policy.retention_years = 7
        policy.save()
        d.refresh_from_db()
        assert d.retention_until == date(2032, 1, 1)


@pytest.mark.django_db
class TestSignatureImmutable:
    def test_signature_pre_save_blocks_changes(self, tenant_a, document, tenant_admin):
        sig = DocumentSignature.objects.create(
            tenant=tenant_a, document=document, signer=tenant_admin,
            typed_name='Original', meaning='approver',
        )
        sig.typed_name = 'Changed'
        with pytest.raises(PermissionError):
            sig.save()


@pytest.mark.django_db
class TestDocumentLockedDelete:
    def test_locked_doc_refuses_delete(self, tenant_a, document):
        Document.all_objects.filter(pk=document.pk).update(is_locked=True)
        document.refresh_from_db()
        with pytest.raises(PermissionError):
            document.delete()
