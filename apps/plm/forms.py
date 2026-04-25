"""ModelForms for PLM CRUD. File-upload forms enforce extension allowlists."""
import os

from django import forms
from django.core.exceptions import ValidationError

from .models import (
    CADDocument, CADDocumentVersion, ECOAttachment, ECOApproval,
    ECOImpactedItem, EngineeringChangeOrder, NPIDeliverable, NPIProject,
    NPIStage, Product, ProductCategory, ProductCompliance, ProductRevision,
    ProductSpecification, ProductVariant,
)


# ---------------- File validation ----------------

CAD_ALLOWED_EXTS = {
    '.pdf', '.dwg', '.dxf', '.step', '.stp', '.iges', '.igs',
    '.png', '.jpg', '.jpeg', '.svg', '.zip',
}
ECO_ATTACH_ALLOWED_EXTS = CAD_ALLOWED_EXTS | {'.docx', '.xlsx', '.txt', '.csv'}
COMPLIANCE_ALLOWED_EXTS = {'.pdf', '.png', '.jpg', '.jpeg', '.zip'}
MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB


def _validate_file(f, allowed_exts, label='file'):
    if not f:
        return
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in allowed_exts:
        raise ValidationError(
            f'Unsupported {label} type "{ext}". Allowed: {", ".join(sorted(allowed_exts))}.'
        )
    if f.size > MAX_UPLOAD_SIZE:
        raise ValidationError(f'{label} too large (max 25 MB).')


# ---------------- Product Master Data ----------------

class ProductCategoryForm(forms.ModelForm):
    class Meta:
        model = ProductCategory
        fields = ('name', 'code', 'parent', 'description', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            qs = ProductCategory.objects.filter(tenant=tenant)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            self.fields['parent'].queryset = qs


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            'sku', 'name', 'category', 'product_type', 'unit_of_measure',
            'description', 'status', 'image',
        )
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['category'].queryset = ProductCategory.objects.filter(
                tenant=tenant, is_active=True,
            )


class ProductRevisionForm(forms.ModelForm):
    class Meta:
        model = ProductRevision
        fields = ('revision_code', 'effective_date', 'status', 'change_notes')
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date'}),
            'change_notes': forms.Textarea(attrs={'rows': 3}),
        }


class ProductSpecificationForm(forms.ModelForm):
    class Meta:
        model = ProductSpecification
        fields = ('spec_type', 'key', 'value', 'unit', 'revision')

    def __init__(self, *args, product=None, **kwargs):
        super().__init__(*args, **kwargs)
        if product is not None:
            self.fields['revision'].queryset = product.revisions.all()
            self.fields['revision'].required = False


class ProductVariantForm(forms.ModelForm):
    attributes_text = forms.CharField(
        required=False, widget=forms.Textarea(attrs={'rows': 3}),
        label='Attributes (key=value, one per line)',
    )

    class Meta:
        model = ProductVariant
        fields = ('variant_sku', 'name', 'status')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.attributes:
            lines = [f'{k}={v}' for k, v in self.instance.attributes.items()]
            self.fields['attributes_text'].initial = '\n'.join(lines)

    def save(self, commit=True):
        obj = super().save(commit=False)
        text = self.cleaned_data.get('attributes_text', '') or ''
        attrs = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or '=' not in line:
                continue
            k, _, v = line.partition('=')
            attrs[k.strip()] = v.strip()
        obj.attributes = attrs
        if commit:
            obj.save()
        return obj


# ---------------- ECO ----------------

class ECOForm(forms.ModelForm):
    class Meta:
        model = EngineeringChangeOrder
        fields = (
            'title', 'description', 'change_type', 'priority',
            'reason', 'target_implementation_date',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'reason': forms.Textarea(attrs={'rows': 3}),
            'target_implementation_date': forms.DateInput(attrs={'type': 'date'}),
        }


class ECOImpactedItemForm(forms.ModelForm):
    class Meta:
        model = ECOImpactedItem
        fields = ('product', 'before_revision', 'after_revision', 'change_summary')
        widgets = {'change_summary': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)
            self.fields['before_revision'].queryset = ProductRevision.objects.filter(tenant=tenant)
            self.fields['after_revision'].queryset = ProductRevision.objects.filter(tenant=tenant)
            self.fields['before_revision'].required = False
            self.fields['after_revision'].required = False


class ECOApprovalForm(forms.ModelForm):
    class Meta:
        model = ECOApproval
        fields = ('approver', 'comment')
        widgets = {'comment': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        from apps.accounts.models import User
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['approver'].queryset = User.objects.filter(
                tenant=tenant, is_active=True,
            )


class ECOAttachmentForm(forms.ModelForm):
    class Meta:
        model = ECOAttachment
        fields = ('title', 'file')

    def clean_file(self):
        f = self.cleaned_data.get('file')
        _validate_file(f, ECO_ATTACH_ALLOWED_EXTS, 'attachment')
        return f


# ---------------- CAD ----------------

class CADDocumentForm(forms.ModelForm):
    class Meta:
        model = CADDocument
        fields = ('drawing_number', 'title', 'product', 'doc_type', 'description', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)
            self.fields['product'].required = False


class CADDocumentVersionForm(forms.ModelForm):
    class Meta:
        model = CADDocumentVersion
        fields = ('version', 'file', 'change_notes', 'status')
        widgets = {'change_notes': forms.Textarea(attrs={'rows': 3})}

    def clean_file(self):
        f = self.cleaned_data.get('file')
        _validate_file(f, CAD_ALLOWED_EXTS, 'CAD file')
        return f


# ---------------- Compliance ----------------

class ProductComplianceForm(forms.ModelForm):
    class Meta:
        model = ProductCompliance
        fields = (
            'product', 'standard', 'status',
            'certification_number', 'issuing_body',
            'issued_date', 'expiry_date', 'certificate_file', 'notes',
        )
        widgets = {
            'issued_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)

    def clean_certificate_file(self):
        f = self.cleaned_data.get('certificate_file')
        _validate_file(f, COMPLIANCE_ALLOWED_EXTS, 'certificate')
        return f


# ---------------- NPI ----------------

class NPIProjectForm(forms.ModelForm):
    class Meta:
        model = NPIProject
        fields = (
            'name', 'description', 'product', 'project_manager',
            'status', 'current_stage',
            'target_launch_date', 'actual_launch_date',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'target_launch_date': forms.DateInput(attrs={'type': 'date'}),
            'actual_launch_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        from apps.accounts.models import User
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)
            self.fields['product'].required = False
            self.fields['project_manager'].queryset = User.objects.filter(
                tenant=tenant, is_active=True,
            )


class NPIStageForm(forms.ModelForm):
    class Meta:
        model = NPIStage
        fields = (
            'stage', 'sequence',
            'planned_start', 'planned_end', 'actual_start', 'actual_end',
            'status', 'gate_decision', 'gate_notes',
        )
        widgets = {
            'planned_start': forms.DateInput(attrs={'type': 'date'}),
            'planned_end': forms.DateInput(attrs={'type': 'date'}),
            'actual_start': forms.DateInput(attrs={'type': 'date'}),
            'actual_end': forms.DateInput(attrs={'type': 'date'}),
            'gate_notes': forms.Textarea(attrs={'rows': 3}),
        }


class NPIDeliverableForm(forms.ModelForm):
    class Meta:
        model = NPIDeliverable
        fields = ('name', 'description', 'owner', 'due_date', 'status')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        from apps.accounts.models import User
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['owner'].queryset = User.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['owner'].required = False
