"""Module 13 - Compliance & Regulatory Management ModelForms.

Honors:
    - L-01: tenant-scoped forms enforce their own (tenant, ...) clean().
    - L-02: every Decimal carries explicit MinValueValidator.
    - L-14: per-workflow forms enforce per-transition required fields.
    - L-19: file uploads validate extension + content_type + size cap.
"""
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

from . import models


_DOC_MAX_BYTES = 25 * 1024 * 1024  # 25 MiB cap for compliance attachments.
_DOC_ALLOWED_CONTENT_TYPES = {
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'image/png',
    'image/jpeg',
    'application/octet-stream',
}


class TenantForm(forms.ModelForm):
    """Stash request.tenant on self._tenant for clean() use."""

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant


# ============================================================================
# 13.1  EHS
# ============================================================================

class IncidentTypeForm(TenantForm):
    class Meta:
        model = models.IncidentType
        fields = ['code', 'name', 'category', 'description', 'is_active']

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.IncidentType.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'An incident type with this code already exists.')
        return data


class IncidentReportForm(TenantForm):
    class Meta:
        model = models.IncidentReport
        fields = [
            'incident_type', 'title', 'description', 'occurred_at',
            'location', 'severity', 'witnesses', 'immediate_actions',
        ]
        widgets = {
            'occurred_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'description': forms.Textarea(attrs={'rows': 4}),
            'immediate_actions': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            from apps.inventory.models import Warehouse
            self.fields['incident_type'].queryset = (
                models.IncidentType.all_objects.filter(
                    tenant=self._tenant, is_active=True,
                )
            )
            self.fields['location'].queryset = (
                Warehouse.all_objects.filter(tenant=self._tenant)
            )


class IncidentInvestigationForm(forms.Form):
    """L-14: investigation step requires root_cause text."""

    root_cause = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}))

    def clean_root_cause(self):
        v = self.cleaned_data.get('root_cause', '').strip()
        if not v:
            raise ValidationError('Root-cause analysis is required.')
        return v


class IncidentActionForm(forms.Form):
    """L-14: corrective-action step requires corrective_actions text."""

    corrective_actions = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}))

    def clean_corrective_actions(self):
        v = self.cleaned_data.get('corrective_actions', '').strip()
        if not v:
            raise ValidationError('Corrective actions are required.')
        return v


class IncidentCancelForm(forms.Form):
    cancellation_reason = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}))

    def clean_cancellation_reason(self):
        v = self.cleaned_data.get('cancellation_reason', '').strip()
        if not v:
            raise ValidationError('Cancellation reason is required.')
        return v


class RiskAssessmentForm(TenantForm):
    class Meta:
        model = models.RiskAssessment
        fields = [
            'title', 'hazard', 'location', 'likelihood', 'severity',
            'control_measures', 'residual_likelihood', 'residual_severity',
            'notes',
        ]
        widgets = {
            'hazard': forms.Textarea(attrs={'rows': 3}),
            'control_measures': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            from apps.inventory.models import Warehouse
            self.fields['location'].queryset = (
                Warehouse.all_objects.filter(tenant=self._tenant)
            )

    def clean(self):
        data = super().clean()
        rl = data.get('residual_likelihood')
        rs = data.get('residual_severity')
        # Either both residual fields are set or neither.
        if (rl is None) != (rs is None):
            self.add_error(
                'residual_severity',
                'Set both residual likelihood and residual severity, or neither.',
            )
        return data


class SafetyChecklistForm(TenantForm):
    class Meta:
        model = models.SafetyAuditChecklist
        fields = ['code', 'name', 'description', 'is_active']

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.SafetyAuditChecklist.all_objects.filter(
                tenant=self._tenant, code=code,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A checklist with this code already exists.')
        return data


class SafetyChecklistItemForm(forms.Form):
    """One-row form used inline on the checklist detail page to append a question."""

    question = forms.CharField(max_length=400)


class SafetyAuditForm(TenantForm):
    class Meta:
        model = models.SafetyAudit
        fields = ['checklist', 'location', 'scheduled_for', 'auditor', 'notes']
        widgets = {
            'scheduled_for': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            from apps.accounts.models import User
            from apps.inventory.models import Warehouse
            self.fields['checklist'].queryset = (
                models.SafetyAuditChecklist.all_objects.filter(
                    tenant=self._tenant, is_active=True,
                )
            )
            self.fields['location'].queryset = (
                Warehouse.all_objects.filter(tenant=self._tenant)
            )
            self.fields['auditor'].queryset = (
                User.objects.filter(tenant=self._tenant)
            )


class SafetyAuditItemRecordForm(forms.Form):
    """Inline POST: pick a question and record pass/fail/na."""

    item_order = forms.IntegerField(min_value=1)
    question = forms.CharField(max_length=400)
    result = forms.ChoiceField(choices=models.SafetyAuditItem.RESULT_CHOICES)
    finding = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}), required=False,
    )


class SafetyAuditCancelForm(forms.Form):
    cancellation_reason = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}))

    def clean_cancellation_reason(self):
        v = self.cleaned_data.get('cancellation_reason', '').strip()
        if not v:
            raise ValidationError('Cancellation reason is required.')
        return v


# ============================================================================
# 13.2  Documents
# ============================================================================

class ComplianceDocumentForm(TenantForm):
    class Meta:
        model = models.ComplianceDocument
        fields = [
            'doc_type', 'title', 'description', 'version', 'attachment',
            'effective_to', 'notes',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'effective_to': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_attachment(self):
        f = self.cleaned_data.get('attachment')
        if not f:
            return f
        if f.size > _DOC_MAX_BYTES:
            raise ValidationError(
                f'File too large: {f.size} bytes > {_DOC_MAX_BYTES} bytes (25 MiB cap).',
            )
        ctype = (getattr(f, 'content_type', '') or '').lower()
        if ctype and ctype not in _DOC_ALLOWED_CONTENT_TYPES:
            raise ValidationError(
                f'Unsupported content-type: {ctype}.',
            )
        return f


class DocumentApprovalCommentForm(forms.Form):
    """L-14: approve / reject / publish / supersede must capture a comment."""

    comment = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}))

    def clean_comment(self):
        v = self.cleaned_data.get('comment', '').strip()
        if not v:
            raise ValidationError('A comment is required for this action.')
        return v


class ElectronicSignatureForm(forms.Form):
    """FDA 21 CFR §11.50: typed full name + reason + role + password re-auth.

    The view also re-authenticates the user against their session password
    before persisting the signature row.
    """

    typed_name = forms.CharField(max_length=200)
    role = forms.CharField(max_length=120, required=False)
    reason = forms.ChoiceField(choices=models.ElectronicSignature.REASON_CHOICES)
    password = forms.CharField(widget=forms.PasswordInput, required=True)

    def clean_typed_name(self):
        v = self.cleaned_data.get('typed_name', '').strip()
        if not v:
            raise ValidationError('Typed full name is required.')
        if len(v) < 3:
            raise ValidationError('Type your full legal name.')
        return v


# ============================================================================
# 13.3  Audit Trail (read-only viewer; archive generation form)
# ============================================================================

class ArchiveGenerateForm(forms.Form):
    period_start = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    period_end = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        data = super().clean()
        s, e = data.get('period_start'), data.get('period_end')
        if s and e and e < s:
            self.add_error('period_end', 'Must be on or after period start.')
        return data


# ============================================================================
# 13.4  Waste
# ============================================================================

class WasteCategoryForm(TenantForm):
    class Meta:
        model = models.WasteCategory
        fields = ['code', 'name', 'hazard_class', 'epa_code', 'description', 'is_active']

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.WasteCategory.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A waste category with this code already exists.')
        return data


class WasteManifestForm(TenantForm):
    class Meta:
        model = models.WasteManifest
        fields = [
            'category', 'generator', 'transporter', 'disposal_facility',
            'epa_id', 'manifest_date', 'pickup_at', 'delivered_at', 'notes',
        ]
        widgets = {
            'manifest_date': forms.DateInput(attrs={'type': 'date'}),
            'pickup_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'delivered_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['category'].queryset = (
                models.WasteCategory.all_objects.filter(
                    tenant=self._tenant, is_active=True,
                )
            )

    def clean(self):
        data = super().clean()
        d = data.get('delivered_at')
        p = data.get('pickup_at')
        if p and d and d < p:
            self.add_error('delivered_at', 'Delivery must be on or after pickup.')
        return data


class WasteDisposalRecordForm(forms.ModelForm):
    """Inline form on manifest detail; tenant set from the parent manifest."""

    class Meta:
        model = models.WasteDisposalRecord
        fields = [
            'line_number', 'description', 'quantity_kg', 'container_type',
            'container_count', 'disposal_method', 'notes',
        ]


class WasteManifestCancelForm(forms.Form):
    cancellation_reason = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}))

    def clean_cancellation_reason(self):
        v = self.cleaned_data.get('cancellation_reason', '').strip()
        if not v:
            raise ValidationError('Cancellation reason is required.')
        return v


# ============================================================================
# 13.5  Recalls
# ============================================================================

class ProductRecallForm(TenantForm):
    class Meta:
        model = models.ProductRecall
        fields = [
            'product', 'title', 'severity', 'root_cause', 'corrective_action',
            'notes',
        ]
        widgets = {
            'root_cause': forms.Textarea(attrs={'rows': 3}),
            'corrective_action': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            from apps.plm.models import Product
            self.fields['product'].queryset = (
                Product.all_objects.filter(tenant=self._tenant)
            )


class AffectedLotForm(forms.Form):
    """Add an inventory.Lot to a recall."""

    lot = forms.ModelChoiceField(queryset=None)
    affected_quantity = forms.DecimalField(
        max_digits=16, decimal_places=4, min_value=Decimal('0'),
    )

    def __init__(self, *args, tenant=None, recall=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.inventory.models import Lot
        if tenant is not None and recall is not None:
            self.fields['lot'].queryset = (
                Lot.all_objects.filter(tenant=tenant, product=recall.product)
            )


class RecallCancelForm(forms.Form):
    cancellation_reason = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}))

    def clean_cancellation_reason(self):
        v = self.cleaned_data.get('cancellation_reason', '').strip()
        if not v:
            raise ValidationError('Cancellation reason is required.')
        return v


class RecallNoticeForm(TenantForm):
    class Meta:
        model = models.RecallNotice
        fields = ['channel', 'audience', 'subject', 'body', 'notes']
        widgets = {
            'body': forms.Textarea(attrs={'rows': 5}),
        }
