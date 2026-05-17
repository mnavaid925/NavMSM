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
    # NOTE D-02: .svg deliberately excluded — SVG is XML and may carry
    # <script>/event-handler payloads → stored XSS via direct file URL.
    # Use PNG/JPG instead for image previews of CAD assets.
    '.pdf', '.dwg', '.dxf', '.step', '.stp', '.iges', '.igs',
    '.png', '.jpg', '.jpeg', '.zip',
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
        self._tenant = tenant
        if tenant is not None:
            qs = ProductCategory.objects.filter(tenant=tenant)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            self.fields['parent'].queryset = qs

    def clean_code(self):
        code = self.cleaned_data.get('code')
        if code and self._tenant is not None:
            qs = ProductCategory.objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    f'A category with code "{code}" already exists in this tenant.'
                )
        return code


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
        self._tenant = tenant
        if tenant is not None:
            self.fields['category'].queryset = ProductCategory.objects.filter(
                tenant=tenant, is_active=True,
            )

    def clean_sku(self):
        sku = self.cleaned_data.get('sku')
        if sku and self._tenant is not None:
            qs = Product.objects.filter(tenant=self._tenant, sku=sku)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    f'A product with SKU "{sku}" already exists in this tenant.'
                )
        return sku


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

    def clean(self):
        """D-01: a revision picked here MUST belong to the chosen product;
        otherwise the ECO's audit trail of impact is corrupt."""
        cleaned = super().clean()
        product = cleaned.get('product')
        for field_name in ('before_revision', 'after_revision'):
            rev = cleaned.get(field_name)
            if rev and product and rev.product_id != product.pk:
                self.add_error(
                    field_name,
                    f'Selected revision belongs to {rev.product.sku}, not {product.sku}.',
                )
        return cleaned


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
        self._tenant = tenant
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)
            self.fields['product'].required = False

    def clean_drawing_number(self):
        dn = self.cleaned_data.get('drawing_number')
        if dn and self._tenant is not None:
            qs = CADDocument.objects.filter(tenant=self._tenant, drawing_number=dn)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    f'A CAD document with drawing number "{dn}" already exists in this tenant.'
                )
        return dn


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
    """ProductCompliance create/edit form.

    When the tenant has `require_compliance_e_signature=True`, transitioning
    a record INTO `status='compliant'` requires the operator to fill in the
    optional `esig_*` fields below. The view writes a
    `plm.ProductComplianceSignature` row from those fields after save (C.8 /
    FDA 21 CFR Part 11).
    """

    esig_typed_name = forms.CharField(
        max_length=200, required=False,
        label='Electronic signature - typed name',
        help_text='Full legal name. Required when transitioning to "Compliant" on a regulated tenant.',
    )
    esig_role = forms.CharField(max_length=120, required=False, label='Signer role')
    esig_reason = forms.ChoiceField(
        choices=[
            ('initial_certification', 'Initial Certification'),
            ('renewal', 'Renewal'),
            ('reaffirmation', 'Reaffirmation'),
            ('correction', 'Correction'),
        ],
        initial='initial_certification', required=False,
        label='Signature reason',
    )

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
        # Stash tenant so clean() can scope the duplicate-check (lessons L-01).
        self._tenant = tenant
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)
            # Hide e-sig fields when the tenant doesn't require them — keeps
            # the existing UI clean for non-regulated tenants.
            if not getattr(tenant, 'require_compliance_e_signature', False):
                for fname in ('esig_typed_name', 'esig_role', 'esig_reason'):
                    self.fields[fname].widget = forms.HiddenInput()

    def clean_certificate_file(self):
        f = self.cleaned_data.get('certificate_file')
        _validate_file(f, COMPLIANCE_ALLOWED_EXTS, 'certificate')
        return f

    def clean(self):
        """D-CR-04 + D-CR-05 guards.

        D-CR-04: reject `expiry_date < issued_date` (silent data corruption).
        D-CR-05: enforce `unique_together = (tenant, product, standard)` at the
                 form layer because `tenant` is set by the view post-`commit=False`
                 and is therefore excluded from Django's `validate_unique()` —
                 the duplicate would otherwise escape to the DB and 500.
                 (Lessons L-01.)
        """
        cleaned = super().clean()

        issued = cleaned.get('issued_date')
        expiry = cleaned.get('expiry_date')
        if issued and expiry and expiry < issued:
            self.add_error(
                'expiry_date',
                'Expiry date must be on or after the issued date.',
            )

        product = cleaned.get('product')
        standard = cleaned.get('standard')
        if self._tenant is not None and product and standard:
            qs = ProductCompliance.objects.filter(
                tenant=self._tenant, product=product, standard=standard,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    'A compliance record for this product + standard already exists.',
                )

        # C.8 — FDA 21 CFR Part 11 e-sig requirement. Only fires when the
        # tenant has opted in AND this submit transitions INTO 'compliant'
        # (either creation directly into compliant or edit from another
        # status into compliant). Re-saves of an already-compliant record
        # without status change do NOT re-prompt.
        require_esig = (
            self._tenant is not None
            and getattr(self._tenant, 'require_compliance_e_signature', False)
            and cleaned.get('status') == 'compliant'
        )
        if require_esig:
            previous_status = (
                self.instance.status
                if self.instance and self.instance.pk
                else None
            )
            transitioning_in = previous_status != 'compliant'
            if transitioning_in:
                if not (cleaned.get('esig_typed_name') or '').strip():
                    self.add_error(
                        'esig_typed_name',
                        'Electronic signature is required when transitioning to "Compliant" '
                        '(FDA 21 CFR Part 11). Type your full legal name.',
                    )
                if not cleaned.get('esig_reason'):
                    self.add_error('esig_reason', 'Signature reason is required.')

        return cleaned


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
