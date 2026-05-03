"""ModelForms for Module 9 - Procurement & Supplier Portal.

Per Lesson L-01, every form whose ``Meta.fields`` excludes ``tenant`` performs
its own duplicate check inside ``clean()``. Per Lesson L-14, per-workflow
required fields are enforced by dedicated ``*WorkflowForm`` classes - not by
toggling ``blank=`` on the model.
"""
from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.plm.models import Product

from . import models


class TenantScopedFormMixin:
    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant


# ============================================================================
# 9.1  Purchase Order Management
# ============================================================================

class SupplierForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.Supplier
        fields = (
            'code', 'name', 'legal_name', 'email', 'phone', 'website', 'tax_id',
            'address', 'country', 'currency', 'payment_terms', 'delivery_terms',
            'is_active', 'is_approved', 'risk_rating', 'notes',
        )
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def clean(self):
        cleaned = super().clean()
        code = cleaned.get('code')
        if self._tenant and code:
            qs = models.Supplier.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A supplier with this code already exists.')
        return cleaned


class SupplierContactForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.SupplierContact
        fields = ('supplier', 'name', 'role', 'email', 'phone', 'is_primary', 'is_active')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['supplier'].queryset = models.Supplier.all_objects.filter(
                tenant=self._tenant,
            )


class PurchaseOrderForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.PurchaseOrder
        fields = (
            'supplier', 'order_date', 'required_date', 'currency',
            'payment_terms', 'delivery_terms', 'priority', 'notes',
            'source_quotation', 'blanket_order',
        )
        widgets = {
            'order_date': forms.DateInput(attrs={'type': 'date'}),
            'required_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['supplier'].queryset = models.Supplier.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )
            self.fields['source_quotation'].queryset = models.SupplierQuotation.all_objects.filter(
                tenant=self._tenant,
            )
            self.fields['blanket_order'].queryset = models.BlanketOrder.all_objects.filter(
                tenant=self._tenant, status='active',
            )
            for opt in ('source_quotation', 'blanket_order'):
                self.fields[opt].required = False

    def clean(self):
        cleaned = super().clean()
        order_date = cleaned.get('order_date')
        required_date = cleaned.get('required_date')
        if order_date and required_date and required_date < order_date:
            self.add_error('required_date', 'Required date cannot be before order date.')
        return cleaned


class PurchaseOrderLineForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.PurchaseOrderLine
        fields = (
            'product', 'description', 'quantity', 'unit_of_measure',
            'unit_price', 'tax_pct', 'discount_pct', 'required_date', 'notes',
        )
        widgets = {
            'required_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['product'].queryset = Product.all_objects.filter(
                tenant=self._tenant,
            ).exclude(status='obsolete')
            self.fields['product'].required = False


class PurchaseOrderApprovalForm(TenantScopedFormMixin, forms.ModelForm):
    """Workflow-specific form for the Approve/Reject action.

    Per Lesson L-14, comments are required when the decision is 'rejected'.
    """

    class Meta:
        model = models.PurchaseOrderApproval
        fields = ('decision', 'comments')
        widgets = {'comments': forms.Textarea(attrs={'rows': 3})}

    def clean(self):
        cleaned = super().clean()
        decision = cleaned.get('decision')
        comments = (cleaned.get('comments') or '').strip()
        if decision == 'rejected' and not comments:
            self.add_error('comments', 'Reason is required when rejecting a PO.')
        return cleaned


# ============================================================================
# 9.2  RFQ & Quotation
# ============================================================================

class RFQForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.RequestForQuotation
        fields = (
            'title', 'description', 'currency', 'issued_date',
            'response_due_date', 'round_number', 'parent_rfq',
        )
        widgets = {
            'issued_date': forms.DateInput(attrs={'type': 'date'}),
            'response_due_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['parent_rfq'].queryset = (
                models.RequestForQuotation.all_objects.filter(tenant=self._tenant)
            )
            self.fields['parent_rfq'].required = False

    def clean(self):
        cleaned = super().clean()
        issued = cleaned.get('issued_date')
        due = cleaned.get('response_due_date')
        if issued and due and due < issued:
            self.add_error('response_due_date', 'Response due date cannot be before issued date.')
        return cleaned


class RFQLineForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.RFQLine
        fields = (
            'product', 'description', 'quantity', 'unit_of_measure',
            'target_price', 'required_date',
        )
        widgets = {'required_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['product'].queryset = Product.all_objects.filter(tenant=self._tenant)
            self.fields['product'].required = False


class RFQSupplierForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.RFQSupplier
        fields = ('supplier',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['supplier'].queryset = models.Supplier.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )


class SupplierQuotationForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.SupplierQuotation
        fields = (
            'rfq', 'supplier', 'quote_date', 'valid_until', 'currency',
            'payment_terms', 'delivery_terms', 'notes',
        )
        widgets = {
            'quote_date': forms.DateInput(attrs={'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['rfq'].queryset = models.RequestForQuotation.all_objects.filter(
                tenant=self._tenant,
            )
            self.fields['supplier'].queryset = models.Supplier.all_objects.filter(
                tenant=self._tenant,
            )

    def clean(self):
        cleaned = super().clean()
        qd = cleaned.get('quote_date')
        vu = cleaned.get('valid_until')
        if qd and vu and vu < qd:
            self.add_error('valid_until', 'Valid-until cannot be before quote date.')
        rfq = cleaned.get('rfq')
        supplier = cleaned.get('supplier')
        if rfq and supplier:
            qs = models.SupplierQuotation.all_objects.filter(rfq=rfq, supplier=supplier)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    'A quotation from this supplier already exists for this RFQ.'
                )
        return cleaned


class QuotationLineForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.QuotationLine
        fields = ('rfq_line', 'unit_price', 'lead_time_days', 'min_order_qty', 'comments')

    def __init__(self, *args, rfq=None, **kwargs):
        super().__init__(*args, **kwargs)
        if rfq is not None:
            self.fields['rfq_line'].queryset = models.RFQLine.all_objects.filter(rfq=rfq)


class QuotationAwardForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.QuotationAward
        fields = ('quotation', 'award_notes', 'auto_create_po')
        widgets = {'award_notes': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, rfq=None, **kwargs):
        super().__init__(*args, **kwargs)
        if rfq is not None:
            self.fields['quotation'].queryset = models.SupplierQuotation.all_objects.filter(
                rfq=rfq,
            )

    def clean_award_notes(self):
        notes = (self.cleaned_data.get('award_notes') or '').strip()
        if not notes:
            raise forms.ValidationError('Award notes are required for traceability.')
        return notes


# ============================================================================
# 9.4  Supplier Self-Service Portal
# ============================================================================

class SupplierASNForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.SupplierASN
        fields = (
            'purchase_order', 'ship_date', 'expected_arrival_date', 'carrier',
            'tracking_number', 'total_packages', 'notes',
        )
        widgets = {
            'ship_date': forms.DateInput(attrs={'type': 'date'}),
            'expected_arrival_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, supplier=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            qs = models.PurchaseOrder.all_objects.filter(
                tenant=self._tenant,
                status__in=('approved', 'acknowledged', 'in_progress'),
            )
            if supplier is not None:
                qs = qs.filter(supplier=supplier)
            self.fields['purchase_order'].queryset = qs


class SupplierASNLineForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.SupplierASNLine
        fields = ('po_line', 'quantity_shipped', 'lot_number', 'serial_numbers', 'notes')
        widgets = {
            'serial_numbers': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, asn=None, **kwargs):
        super().__init__(*args, **kwargs)
        if asn is not None:
            self.fields['po_line'].queryset = models.PurchaseOrderLine.all_objects.filter(
                po=asn.purchase_order,
            )


class SupplierInvoiceForm(TenantScopedFormMixin, forms.ModelForm):
    ALLOWED_EXT = {'.pdf', '.png', '.jpg', '.jpeg'}
    MAX_BYTES = 25 * 1024 * 1024

    class Meta:
        model = models.SupplierInvoice
        fields = (
            'vendor_invoice_number', 'supplier', 'purchase_order',
            'invoice_date', 'due_date', 'currency',
            'subtotal', 'tax_total', 'grand_total',
            'notes', 'attachment',
        )
        widgets = {
            'invoice_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, supplier=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            sup_qs = models.Supplier.all_objects.filter(tenant=self._tenant)
            self.fields['supplier'].queryset = sup_qs
            po_qs = models.PurchaseOrder.all_objects.filter(tenant=self._tenant)
            if supplier is not None:
                po_qs = po_qs.filter(supplier=supplier)
                self.fields['supplier'].initial = supplier
                self.fields['supplier'].disabled = True
            self.fields['purchase_order'].queryset = po_qs
            self.fields['purchase_order'].required = False

    def clean(self):
        cleaned = super().clean()
        supplier = cleaned.get('supplier')
        vendor_no = (cleaned.get('vendor_invoice_number') or '').strip()
        if supplier and vendor_no:
            qs = models.SupplierInvoice.all_objects.filter(
                supplier=supplier, vendor_invoice_number=vendor_no,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'vendor_invoice_number',
                    'This vendor invoice number is already on file for this supplier.',
                )
        sub = cleaned.get('subtotal') or Decimal('0')
        tax = cleaned.get('tax_total') or Decimal('0')
        grand = cleaned.get('grand_total') or Decimal('0')
        # Soft check: complain only when the user supplied numbers that
        # blatantly contradict each other (off by more than 1 cent).
        if abs((sub + tax) - grand) > Decimal('0.01'):
            self.add_error(
                'grand_total', 'Grand total should equal subtotal + tax.',
            )
        return cleaned

    def clean_attachment(self):
        f = self.cleaned_data.get('attachment')
        if not f:
            return f
        name = f.name.lower()
        if not any(name.endswith(ext) for ext in self.ALLOWED_EXT):
            raise forms.ValidationError(
                f'Unsupported file type. Allowed: {", ".join(sorted(self.ALLOWED_EXT))}'
            )
        if f.size > self.MAX_BYTES:
            raise forms.ValidationError('File exceeds 25 MB cap.')
        return f


class SupplierInvoiceWorkflowForm(forms.Form):
    """Per Lesson L-14, payment_reference is required when transitioning to paid."""

    payment_reference = forms.CharField(max_length=120, required=False)
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)

    def __init__(self, *args, action=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._action = action

    def clean(self):
        cleaned = super().clean()
        if self._action == 'paid':
            ref = (cleaned.get('payment_reference') or '').strip()
            if not ref:
                self.add_error('payment_reference', 'Payment reference required to mark paid.')
        return cleaned


# ============================================================================
# 9.5  Blanket Orders & Releases
# ============================================================================

class BlanketOrderForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.BlanketOrder
        fields = (
            'supplier', 'start_date', 'end_date', 'currency',
            'total_committed_value', 'notes',
        )
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['supplier'].queryset = models.Supplier.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )

    def clean(self):
        cleaned = super().clean()
        sd = cleaned.get('start_date')
        ed = cleaned.get('end_date')
        if sd and ed and ed < sd:
            self.add_error('end_date', 'End date cannot be before start date.')
        return cleaned


class BlanketOrderLineForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.BlanketOrderLine
        fields = ('product', 'description', 'total_quantity', 'unit_of_measure', 'unit_price', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['product'].queryset = Product.all_objects.filter(
                tenant=self._tenant,
            ).exclude(status='obsolete')


class ScheduleReleaseForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.ScheduleRelease
        fields = ('blanket_order', 'release_date', 'required_date', 'notes')
        widgets = {
            'release_date': forms.DateInput(attrs={'type': 'date'}),
            'required_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['blanket_order'].queryset = models.BlanketOrder.all_objects.filter(
                tenant=self._tenant, status='active',
            )


class ScheduleReleaseLineForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.ScheduleReleaseLine
        fields = ('blanket_order_line', 'quantity', 'required_date')
        widgets = {'required_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, release=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._release = release
        if release is not None:
            self.fields['blanket_order_line'].queryset = (
                models.BlanketOrderLine.all_objects.filter(blanket_order=release.blanket_order)
            )

    def clean(self):
        cleaned = super().clean()
        bol = cleaned.get('blanket_order_line')
        qty = cleaned.get('quantity') or Decimal('0')
        if bol and qty:
            # Sum existing release lines (excluding self) against this blanket line.
            siblings = models.ScheduleReleaseLine.all_objects.filter(
                blanket_order_line=bol,
            )
            if self.instance.pk:
                siblings = siblings.exclude(pk=self.instance.pk)
            already = sum(
                (s.quantity for s in siblings if s.release.status != 'cancelled'),
                Decimal('0'),
            )
            if already + qty > bol.total_quantity:
                remaining = bol.total_quantity - already
                self.add_error(
                    'quantity',
                    f'Exceeds blanket commitment. Remaining: {remaining}.',
                )
        return cleaned
