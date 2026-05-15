"""Model invariants + auto-numbering + computed fields."""
from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError

from apps.dms.models import (
    ApprovalWorkflow,
    AssignmentTarget,
    Document,
    DocumentAccessRule,
    DocumentArchive,
    DocumentAssignment,
    DocumentCategory,
    DocumentSignature,
    DocumentTemplate,
    DocumentVersion,
    LegalHold,
    ReadAcknowledgment,
    RetentionPolicy,
)


@pytest.mark.django_db
class TestAutoNumbering:
    def test_document_code(self, tenant_a):
        d = Document.objects.create(tenant=tenant_a, title='Doc 1')
        assert d.code.startswith('DOC-')
        d2 = Document.objects.create(tenant=tenant_a, title='Doc 2')
        assert d2.code != d.code

    def test_template_code(self, tenant_a):
        t = DocumentTemplate.objects.create(tenant=tenant_a, name='T1')
        assert t.code.startswith('TPL-')

    def test_retention_policy_code(self, tenant_a):
        p = RetentionPolicy.objects.create(tenant=tenant_a, name='P1', retention_years=5)
        assert p.code.startswith('RP-')

    def test_assignment_code(self, tenant_a, document):
        a = DocumentAssignment.objects.create(tenant=tenant_a, document=document)
        assert a.code.startswith('DA-')

    def test_archive_code(self, tenant_a, document):
        a = DocumentArchive.objects.create(tenant=tenant_a, document=document)
        assert a.code.startswith('ARC-')

    def test_legal_hold_code(self, tenant_a):
        h = LegalHold.objects.create(tenant=tenant_a, name='Hold 1')
        assert h.code.startswith('LH-')


@pytest.mark.django_db
class TestDocumentHelpers:
    def test_is_editable_states(self, tenant_a):
        d = Document.objects.create(tenant=tenant_a, title='X', status='draft')
        DocumentVersion.objects.create(tenant=tenant_a, document=d, version='1')
        assert d.is_editable()
        d.status = 'in_review'
        assert d.is_editable()
        d.status = 'effective'
        assert not d.is_editable()
        d.status = 'archived'
        assert not d.is_editable()

    def test_is_editable_locked(self, tenant_a):
        d = Document.objects.create(tenant=tenant_a, title='X', status='draft', is_locked=True)
        assert not d.is_editable()

    def test_can_submit_requires_versions(self, tenant_a):
        d = Document.objects.create(tenant=tenant_a, title='X', status='draft')
        assert not d.can_submit()
        DocumentVersion.objects.create(tenant=tenant_a, document=d, version='1')
        # Refresh because relation is cached.
        d = Document.objects.get(pk=d.pk)
        assert d.can_submit()

    def test_can_archive_blocks_when_locked(self, tenant_a):
        d = Document.objects.create(tenant=tenant_a, title='X', is_locked=True)
        assert not d.can_archive()

    def test_is_expiring_soon(self, tenant_a):
        d = Document.objects.create(
            tenant=tenant_a, title='X',
            expiry_date=date.today() + timedelta(days=10),
        )
        assert d.is_expiring_soon()
        d.expiry_date = date.today() + timedelta(days=90)
        assert not d.is_expiring_soon()


@pytest.mark.django_db
class TestUniqueTogether:
    def test_category_code_unique_per_tenant(self, tenant_a, tenant_b):
        DocumentCategory.objects.create(tenant=tenant_a, code='X', name='X')
        DocumentCategory.objects.create(tenant=tenant_b, code='X', name='X')  # different tenant OK
        with pytest.raises(Exception):
            DocumentCategory.objects.create(tenant=tenant_a, code='X', name='Y')

    def test_template_name_unique_per_tenant(self, tenant_a, tenant_b):
        DocumentTemplate.objects.create(tenant=tenant_a, name='T')
        DocumentTemplate.objects.create(tenant=tenant_b, name='T')
        with pytest.raises(Exception):
            DocumentTemplate.objects.create(tenant=tenant_a, name='T')

    def test_workflow_name_unique_per_tenant(self, tenant_a):
        ApprovalWorkflow.objects.create(tenant=tenant_a, name='W')
        with pytest.raises(Exception):
            ApprovalWorkflow.objects.create(tenant=tenant_a, name='W')


@pytest.mark.django_db
class TestVersionInvariants:
    def test_version_str(self, version):
        assert str(version) == f'{version.document.code} v1.0'

    def test_version_locked_after_checkout(self, tenant_a, document, tenant_admin):
        v = DocumentVersion.objects.create(tenant=tenant_a, document=document, version='2')
        assert not v.is_locked()
        v.checked_out_by = tenant_admin
        assert v.is_locked()


@pytest.mark.django_db
class TestAssignmentTargetXor:
    def test_xor_valid_single(self, tenant_a, document):
        a = DocumentAssignment.objects.create(tenant=tenant_a, document=document)
        t = AssignmentTarget.objects.create(tenant=tenant_a, assignment=a, role='operator')
        assert t.is_xor_valid

    def test_xor_invalid_when_multiple(self, tenant_a, document, department, tenant_admin):
        a = DocumentAssignment.objects.create(tenant=tenant_a, document=document)
        t = AssignmentTarget(
            tenant=tenant_a, assignment=a,
            role='operator', department=department, user=tenant_admin,
        )
        assert not t.is_xor_valid


@pytest.mark.django_db
class TestRetentionPolicyValidator:
    def test_negative_years_rejected_via_form(self, tenant_a):
        # Use full_clean to invoke validators.
        p = RetentionPolicy(tenant=tenant_a, name='X', retention_years=-1)
        with pytest.raises(ValidationError):
            p.full_clean()


@pytest.mark.django_db
class TestSignatureImmutability:
    def test_signature_save_blocks_update(self, tenant_a, document, tenant_admin):
        sig = DocumentSignature.objects.create(
            tenant=tenant_a, document=document, signer=tenant_admin,
            meaning='approver', typed_name='Test User',
        )
        sig.typed_name = 'Hacked'
        with pytest.raises(PermissionError):
            sig.save()
