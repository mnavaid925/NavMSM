"""Forms for Module 19 - Document & Knowledge Management.

Every tenant-scoped ModelForm whose `Meta.fields` excludes `tenant` and
has a `unique_together` touching `tenant` carries an explicit `clean()`
duplicate check (L-01). FK querysets are filtered per-tenant in __init__.
File uploads enforce 25 MB cap + allowlist (L-22).
"""
from __future__ import annotations

from django import forms

from .models import (
    ApprovalStage,
    ApprovalWorkflow,
    AssignmentTarget,
    DOC_FILE_ALLOWLIST,
    Document,
    DocumentApprovalRequest,
    DocumentArchive,
    DocumentAccessRule,
    DocumentAssignment,
    DocumentCategory,
    DocumentTemplate,
    DocumentVersion,
    LegalHold,
    MEDIA_FILE_ALLOWLIST,
    MediaAttachment,
    ReadAcknowledgment,
    RetentionPolicy,
    TemplateField,
)

# 25 MB cap for every FileField in the module (L-22).
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _validate_uploaded_file(f, allowlist):
    """Common file-validator: size cap + extension allowlist."""
    if not f:
        return
    if f.size > MAX_UPLOAD_BYTES:
        raise forms.ValidationError(
            'File too large (max 25 MB).',
        )
    name = (getattr(f, 'name', '') or '').lower()
    ext = name.rsplit('.', 1)[-1] if '.' in name else ''
    if ext not in allowlist:
        raise forms.ValidationError(
            f'Unsupported extension ".{ext}". Allowed: {", ".join(allowlist)}.',
        )


# ===========================================================================
# 19.1  Controlled Document Repository
# ===========================================================================

class DocumentCategoryForm(forms.ModelForm):
    class Meta:
        model = DocumentCategory
        fields = ('name', 'code', 'parent', 'description', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if tenant is not None:
            self.fields['parent'].queryset = DocumentCategory.objects.filter(
                tenant=tenant,
            ).exclude(pk=self.instance.pk or 0)
            self.fields['parent'].required = False

    def clean(self):
        cleaned = super().clean()
        if self._tenant and cleaned.get('code'):
            qs = DocumentCategory.objects.filter(
                tenant=self._tenant, code=cleaned['code'],
            ).exclude(pk=self.instance.pk or 0)
            if qs.exists():
                raise forms.ValidationError(
                    'A document category with this code already exists.',
                )
        return cleaned


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = (
            'title', 'doc_type', 'category', 'owner',
            'effective_date', 'expiry_date', 'retention_policy',
            'summary', 'keywords', 'is_active',
        )
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'summary': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['category'].queryset = DocumentCategory.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['retention_policy'].queryset = RetentionPolicy.objects.filter(
                tenant=tenant, is_active=True,
            )
            from apps.accounts.models import User
            self.fields['owner'].queryset = User.objects.filter(
                tenant=tenant, is_active=True,
            )
            for opt in ('category', 'owner', 'retention_policy'):
                self.fields[opt].required = False


class DocumentVersionForm(forms.ModelForm):
    class Meta:
        model = DocumentVersion
        fields = ('version', 'file', 'content_html', 'change_notes')
        widgets = {
            'content_html': forms.Textarea(attrs={'rows': 6}),
            'change_notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_file(self):
        f = self.cleaned_data.get('file')
        _validate_uploaded_file(f, DOC_FILE_ALLOWLIST)
        return f

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('file') and not (cleaned.get('content_html') or '').strip():
            raise forms.ValidationError(
                'Either upload a file or provide an in-app content body.',
            )
        return cleaned


class DocumentAccessRuleForm(forms.ModelForm):
    class Meta:
        model = DocumentAccessRule
        fields = ('role', 'user', 'department', 'position')

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            from apps.accounts.models import User
            from apps.labor.models import Department, Position
            self.fields['user'].queryset = User.objects.filter(tenant=tenant)
            self.fields['department'].queryset = Department.objects.filter(tenant=tenant)
            self.fields['position'].queryset = Position.objects.filter(tenant=tenant)
            for opt in ('user', 'department', 'position'):
                self.fields[opt].required = False

    def clean(self):
        cleaned = super().clean()
        flags = [
            bool(cleaned.get('user')),
            bool(cleaned.get('department')),
            bool(cleaned.get('position')),
        ]
        if sum(flags) != 1:
            raise forms.ValidationError(
                'Set exactly one of User, Department, or Position.',
            )
        return cleaned


# ===========================================================================
# 19.2  SOP & Work Instruction Authoring
# ===========================================================================

class DocumentTemplateForm(forms.ModelForm):
    class Meta:
        model = DocumentTemplate
        fields = ('name', 'applies_to_doc_type', 'body', 'is_active')
        widgets = {'body': forms.Textarea(attrs={'rows': 8})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant

    def clean(self):
        cleaned = super().clean()
        if self._tenant and cleaned.get('name'):
            qs = DocumentTemplate.objects.filter(
                tenant=self._tenant, name=cleaned['name'],
            ).exclude(pk=self.instance.pk or 0)
            if qs.exists():
                raise forms.ValidationError(
                    'A document template with this name already exists.',
                )
        return cleaned


class TemplateFieldForm(forms.ModelForm):
    class Meta:
        model = TemplateField
        fields = ('field_name', 'label', 'field_type', 'choices', 'is_required', 'order')
        widgets = {'choices': forms.Textarea(attrs={'rows': 3})}


class MediaAttachmentForm(forms.ModelForm):
    class Meta:
        model = MediaAttachment
        fields = ('media_type', 'file', 'video_url', 'caption', 'order')

    def clean_file(self):
        f = self.cleaned_data.get('file')
        _validate_uploaded_file(f, MEDIA_FILE_ALLOWLIST)
        return f

    def clean_video_url(self):
        url = (self.cleaned_data.get('video_url') or '').strip()
        if url and not (url.startswith('http://') or url.startswith('https://')):
            raise forms.ValidationError('Video URL must start with http:// or https://')
        return url


# ===========================================================================
# 19.3  Document Approval Workflows
# ===========================================================================

class ApprovalWorkflowForm(forms.ModelForm):
    class Meta:
        model = ApprovalWorkflow
        fields = ('name', 'description', 'applies_to_doc_type', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant

    def clean(self):
        cleaned = super().clean()
        if self._tenant and cleaned.get('name'):
            qs = ApprovalWorkflow.objects.filter(
                tenant=self._tenant, name=cleaned['name'],
            ).exclude(pk=self.instance.pk or 0)
            if qs.exists():
                raise forms.ValidationError(
                    'An approval workflow with this name already exists.',
                )
        return cleaned


class ApprovalStageForm(forms.ModelForm):
    class Meta:
        model = ApprovalStage
        fields = (
            'stage_no', 'name', 'approver_role',
            'min_approvals', 'requires_signature',
        )


class DocumentApprovalRequestForm(forms.ModelForm):
    class Meta:
        model = DocumentApprovalRequest
        fields = ('document', 'workflow', 'effective_date', 'notes')
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['document'].queryset = Document.objects.filter(
                tenant=tenant,
            ).exclude(status='archived')
            self.fields['workflow'].queryset = ApprovalWorkflow.objects.filter(
                tenant=tenant, is_active=True,
            )

    def clean(self):
        cleaned = super().clean()
        doc = cleaned.get('document')
        if doc and not self.instance.pk:
            open_exists = DocumentApprovalRequest.objects.filter(
                tenant=doc.tenant, document=doc,
                status__in=('pending', 'in_progress'),
            ).exists()
            if open_exists:
                raise forms.ValidationError(
                    'This document already has an open approval request.',
                )
        return cleaned


class ApprovalActionForm(forms.Form):
    """Per-stage decision capture (drives signature creation when required)."""
    DECISION_CHOICES = [
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('return_for_revision', 'Return for revision'),
    ]
    decision = forms.ChoiceField(choices=DECISION_CHOICES)
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    typed_name = forms.CharField(
        max_length=160,
        required=False,
        help_text='Type your full name to record an e-signature.',
    )

    def clean(self):
        cleaned = super().clean()
        decision = cleaned.get('decision')
        notes = (cleaned.get('notes') or '').strip()
        if decision in ('reject', 'return_for_revision') and not notes:
            raise forms.ValidationError(
                'Notes are required when rejecting or returning for revision.',
            )
        return cleaned


# ===========================================================================
# 19.4  Training Document Assignment
# ===========================================================================

class DocumentAssignmentForm(forms.ModelForm):
    class Meta:
        model = DocumentAssignment
        fields = ('document', 'due_date', 'instructions')
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'instructions': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['document'].queryset = Document.objects.filter(
                tenant=tenant, status__in=('approved', 'effective'),
            )


class AssignmentTargetForm(forms.ModelForm):
    class Meta:
        model = AssignmentTarget
        fields = ('role', 'department', 'position', 'employee', 'user')

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            from apps.accounts.models import User
            from apps.labor.models import Department, Employee, Position
            self.fields['department'].queryset = Department.objects.filter(tenant=tenant)
            self.fields['position'].queryset = Position.objects.filter(tenant=tenant)
            self.fields['employee'].queryset = Employee.objects.filter(tenant=tenant)
            self.fields['user'].queryset = User.objects.filter(tenant=tenant)
            for opt in ('department', 'position', 'employee', 'user'):
                self.fields[opt].required = False

    def clean(self):
        cleaned = super().clean()
        flags = [
            bool(cleaned.get('role')),
            bool(cleaned.get('department')),
            bool(cleaned.get('position')),
            bool(cleaned.get('employee')),
            bool(cleaned.get('user')),
        ]
        if sum(flags) != 1:
            raise forms.ValidationError(
                'Set exactly one target: Role, Department, Position, Employee, or User.',
            )
        return cleaned


class ReadAcknowledgmentForm(forms.Form):
    """User-facing typed-signature ack form."""
    typed_name = forms.CharField(
        max_length=160,
        help_text='Type your full name to confirm you have read this document.',
    )
    notes = forms.CharField(
        required=False, widget=forms.Textarea(attrs={'rows': 2}),
    )


# ===========================================================================
# 19.5  Archive & Retention Policy
# ===========================================================================

class RetentionPolicyForm(forms.ModelForm):
    class Meta:
        model = RetentionPolicy
        fields = (
            'name', 'applies_to_doc_type', 'retention_years',
            'archive_action', 'legal_hold_compatible',
            'description', 'is_active',
        )
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant

    def clean(self):
        cleaned = super().clean()
        if self._tenant and cleaned.get('name'):
            qs = RetentionPolicy.objects.filter(
                tenant=self._tenant, name=cleaned['name'],
            ).exclude(pk=self.instance.pk or 0)
            if qs.exists():
                raise forms.ValidationError(
                    'A retention policy with this name already exists.',
                )
        return cleaned


class LegalHoldForm(forms.ModelForm):
    class Meta:
        model = LegalHold
        fields = ('name', 'reason', 'documents')
        widgets = {'reason': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['documents'].queryset = Document.objects.filter(
                tenant=tenant,
            ).exclude(status='archived')


class LegalHoldReleaseForm(forms.Form):
    """L-14: releasing a hold requires release notes for the audit trail."""
    release_notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Reason for releasing this hold. Required.',
    )


class DocumentArchiveForm(forms.ModelForm):
    class Meta:
        model = DocumentArchive
        fields = ('notes',)
        widgets = {'notes': forms.Textarea(attrs={'rows': 3})}


class DocumentArchiveRestoreForm(forms.Form):
    """L-14: restoring an archive requires a justification note."""
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Reason for restoring this archived document. Required.',
    )
