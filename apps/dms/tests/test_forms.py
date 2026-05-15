"""Form validation: L-01 unique_together, XOR validators, file caps (L-22)."""
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.dms.forms import (
    AssignmentTargetForm,
    DocumentAccessRuleForm,
    DocumentApprovalRequestForm,
    DocumentArchiveRestoreForm,
    DocumentCategoryForm,
    DocumentTemplateForm,
    DocumentVersionForm,
    LegalHoldReleaseForm,
    MediaAttachmentForm,
    RetentionPolicyForm,
)
from apps.dms.models import (
    ApprovalWorkflow, DocumentCategory, DocumentTemplate, RetentionPolicy,
)


@pytest.mark.django_db
class TestUniqueTogetherCleans:
    def test_category_duplicate_code_rejected(self, tenant_a):
        DocumentCategory.objects.create(tenant=tenant_a, code='X', name='X')
        form = DocumentCategoryForm(
            data={'name': 'Other', 'code': 'X', 'is_active': 'on'},
            tenant=tenant_a,
        )
        assert not form.is_valid()
        assert 'already exists' in str(form.errors)

    def test_template_duplicate_name_rejected(self, tenant_a):
        DocumentTemplate.objects.create(tenant=tenant_a, name='T1')
        form = DocumentTemplateForm(
            data={'name': 'T1', 'applies_to_doc_type': 'sop', 'body': 'x', 'is_active': 'on'},
            tenant=tenant_a,
        )
        assert not form.is_valid()

    def test_policy_duplicate_name_rejected(self, tenant_a):
        RetentionPolicy.objects.create(tenant=tenant_a, name='P', retention_years=5)
        form = RetentionPolicyForm(
            data={
                'name': 'P', 'applies_to_doc_type': 'any',
                'retention_years': 7, 'archive_action': 'archive',
                'legal_hold_compatible': 'on', 'is_active': 'on',
            },
            tenant=tenant_a,
        )
        assert not form.is_valid()


@pytest.mark.django_db
class TestAccessRuleXor:
    def test_zero_targets_rejected(self, tenant_a, document):
        form = DocumentAccessRuleForm(
            data={'role': 'viewer'},
            tenant=tenant_a,
        )
        assert not form.is_valid()
        assert 'exactly one' in str(form.errors).lower()

    def test_two_targets_rejected(self, tenant_a, document, department, tenant_admin):
        form = DocumentAccessRuleForm(
            data={
                'role': 'viewer',
                'user': tenant_admin.pk,
                'department': department.pk,
            },
            tenant=tenant_a,
        )
        assert not form.is_valid()


@pytest.mark.django_db
class TestAssignmentTargetXor:
    def test_zero_targets_rejected(self, tenant_a):
        form = AssignmentTargetForm(data={}, tenant=tenant_a)
        assert not form.is_valid()

    def test_one_target_ok(self, tenant_a):
        form = AssignmentTargetForm(data={'role': 'operator'}, tenant=tenant_a)
        assert form.is_valid(), form.errors

    def test_two_targets_rejected(self, tenant_a, tenant_admin, department):
        form = AssignmentTargetForm(
            data={'role': 'operator', 'user': tenant_admin.pk},
            tenant=tenant_a,
        )
        assert not form.is_valid()


@pytest.mark.django_db
class TestFileCap:
    def test_version_oversize_file_rejected(self, tenant_a):
        # 26 MB > 25 MB cap
        big = SimpleUploadedFile('big.pdf', b'x' * (26 * 1024 * 1024), content_type='application/pdf')
        form = DocumentVersionForm(
            data={'version': '1', 'content_html': '', 'change_notes': ''},
            files={'file': big},
        )
        assert not form.is_valid()
        assert 'too large' in str(form.errors).lower()

    def test_version_bad_extension_rejected(self, tenant_a):
        f = SimpleUploadedFile('payload.exe', b'MZ', content_type='application/octet-stream')
        form = DocumentVersionForm(
            data={'version': '1', 'content_html': '', 'change_notes': ''},
            files={'file': f},
        )
        assert not form.is_valid()

    def test_version_needs_file_or_content(self):
        form = DocumentVersionForm(
            data={'version': '1', 'content_html': '', 'change_notes': ''},
        )
        assert not form.is_valid()

    def test_version_content_only_ok(self):
        form = DocumentVersionForm(
            data={'version': '1', 'content_html': 'Body', 'change_notes': ''},
        )
        assert form.is_valid(), form.errors

    def test_media_video_url_scheme_validated(self):
        form = MediaAttachmentForm(
            data={'media_type': 'video', 'video_url': 'javascript:alert(1)', 'caption': '', 'order': 0},
        )
        assert not form.is_valid()


@pytest.mark.django_db
class TestWorkflowL14Required:
    def test_legal_hold_release_requires_notes(self):
        form = LegalHoldReleaseForm(data={'release_notes': ''})
        assert not form.is_valid()

    def test_legal_hold_release_with_notes_ok(self):
        form = LegalHoldReleaseForm(data={'release_notes': 'Audit done.'})
        assert form.is_valid()

    def test_archive_restore_requires_notes(self):
        form = DocumentArchiveRestoreForm(data={'notes': ''})
        assert not form.is_valid()


@pytest.mark.django_db
class TestApprovalRequestForm:
    def test_blocks_second_open_request(self, tenant_a, document, workflow_with_stages):
        from apps.dms.models import DocumentApprovalRequest
        DocumentApprovalRequest.objects.create(
            tenant=tenant_a, document=document, workflow=workflow_with_stages,
            status='in_progress',
        )
        form = DocumentApprovalRequestForm(
            data={
                'document': document.pk,
                'workflow': workflow_with_stages.pk,
                'effective_date': '',
                'notes': '',
            },
            tenant=tenant_a,
        )
        assert not form.is_valid()
        assert 'already has an open' in str(form.errors).lower()


@pytest.mark.django_db
class TestTenantScopedQuerysets:
    def test_workflow_form_filters_to_tenant(self, tenant_a, tenant_b, document):
        ApprovalWorkflow.objects.create(tenant=tenant_b, name='other-tenant')
        form = DocumentApprovalRequestForm(tenant=tenant_a)
        names = [w.name for w in form.fields['workflow'].queryset]
        assert 'other-tenant' not in names
