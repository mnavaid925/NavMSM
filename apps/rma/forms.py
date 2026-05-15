"""Forms for Module 18 - Returns & RMA Management.

Every tenant-scoped ModelForm whose `Meta.fields` excludes `tenant` and
has a `unique_together` touching `tenant` carries an explicit `clean()`
duplicate check (L-01). FK querysets are filtered per-tenant in __init__.
"""
from django import forms

from .models import (
    FailureMode,
    RMALine,
    RMARequest,
    RMAReason,
    RepairLaborLog,
    RepairOrder,
    RepairPartUsage,
    ReturnAnalysis,
    ReturnReceipt,
    ReturnReceiptLine,
    RootCauseCategory,
    SupplierChargeback,
    WarrantyClaim,
    WarrantyPolicy,
    WarrantyRegistration,
)


# ===========================================================================
# 18.1  RMA Request & Authorization
# ===========================================================================

class RMAReasonForm(forms.ModelForm):
    class Meta:
        model = RMAReason
        fields = ('name', 'category', 'description', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant

    def clean(self):
        cleaned = super().clean()
        if self._tenant and cleaned.get('name'):
            qs = RMAReason.objects.filter(
                tenant=self._tenant, name=cleaned['name'],
            ).exclude(pk=self.instance.pk or 0)
            if qs.exists():
                raise forms.ValidationError(
                    'A return reason with this name already exists.',
                )
        return cleaned


class RMARequestForm(forms.ModelForm):
    class Meta:
        model = RMARequest
        fields = (
            'customer', 'sales_order', 'sales_invoice',
            'request_date', 'requested_action',
            'customer_reference', 'reason_summary',
            'customer_notes', 'internal_notes',
        )
        widgets = {
            'request_date': forms.DateInput(attrs={'type': 'date'}),
            'customer_notes': forms.Textarea(attrs={'rows': 3}),
            'internal_notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            from apps.sales.models import Customer, SalesInvoice, SalesOrder
            self.fields['customer'].queryset = Customer.objects.filter(
                tenant=tenant,
            ).exclude(status='blacklisted')
            self.fields['sales_order'].queryset = SalesOrder.objects.filter(tenant=tenant)
            self.fields['sales_invoice'].queryset = SalesInvoice.objects.filter(tenant=tenant)
            self.fields['sales_order'].required = False
            self.fields['sales_invoice'].required = False


class RMALineForm(forms.ModelForm):
    class Meta:
        model = RMALine
        fields = (
            'product', 'quantity', 'unit_price', 'reason',
            'condition_reported', 'lot_number', 'serial_number', 'line_notes',
        )
        widgets = {'line_notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            from apps.plm.models import Product
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)
            self.fields['reason'].queryset = RMAReason.objects.filter(
                tenant=tenant, is_active=True,
            )


# ===========================================================================
# 18.2  Returns Receiving & Inspection
# ===========================================================================

class ReturnReceiptForm(forms.ModelForm):
    class Meta:
        model = ReturnReceipt
        fields = (
            'rma', 'warehouse', 'received_date',
            'carrier_name', 'tracking_number', 'notes',
        )
        widgets = {
            'received_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['rma'].queryset = RMARequest.objects.filter(
                tenant=tenant, status='approved',
            )
            from apps.inventory.models import Warehouse
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant)


class ReturnReceiptLineForm(forms.ModelForm):
    class Meta:
        model = ReturnReceiptLine
        fields = (
            'rma_line', 'quantity_received', 'condition_assessed',
            'disposition', 'inspection_notes',
        )
        widgets = {'inspection_notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, receipt=None, **kwargs):
        super().__init__(*args, **kwargs)
        if receipt is not None:
            self.fields['rma_line'].queryset = receipt.rma.lines.all()


# ===========================================================================
# 18.3  Repair & Refurbishment Tracking
# ===========================================================================

class RepairOrderForm(forms.ModelForm):
    class Meta:
        model = RepairOrder
        fields = (
            'receipt_line', 'product', 'order_type', 'assigned_to',
            'problem_description', 'repair_instructions', 'estimated_cost',
        )
        widgets = {
            'problem_description': forms.Textarea(attrs={'rows': 3}),
            'repair_instructions': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            from apps.plm.models import Product
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)
            self.fields['receipt_line'].queryset = ReturnReceiptLine.objects.filter(
                tenant=tenant, disposition__in=('repair', 'refurbish'),
            )
            self.fields['receipt_line'].required = False


class RepairCompleteForm(forms.Form):
    """Repair completion requires a resolution note for traceability (L-14)."""
    resolution_notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='What was done to resolve the fault. Required.',
    )


class RepairPartUsageForm(forms.ModelForm):
    class Meta:
        model = RepairPartUsage
        fields = ('part', 'quantity', 'unit_cost', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            from apps.plm.models import Product
            self.fields['part'].queryset = Product.objects.filter(tenant=tenant)


class RepairLaborLogForm(forms.ModelForm):
    class Meta:
        model = RepairLaborLog
        fields = ('employee', 'work_date', 'minutes', 'hourly_rate', 'notes')
        widgets = {
            'work_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            from apps.labor.models import Employee
            self.fields['employee'].queryset = Employee.objects.filter(tenant=tenant)
            self.fields['employee'].required = False


# ===========================================================================
# 18.4  Warranty Management
# ===========================================================================

class WarrantyPolicyForm(forms.ModelForm):
    class Meta:
        model = WarrantyPolicy
        fields = (
            'name', 'coverage_type', 'duration_months', 'terms',
            'product', 'product_category', 'is_active',
        )
        widgets = {'terms': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            from apps.plm.models import Product, ProductCategory
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)
            self.fields['product_category'].queryset = ProductCategory.objects.filter(
                tenant=tenant,
            )


class WarrantyRegistrationForm(forms.ModelForm):
    class Meta:
        model = WarrantyRegistration
        fields = (
            'product', 'customer', 'policy', 'sales_order',
            'serial_number', 'purchase_date', 'start_date', 'status', 'notes',
        )
        widgets = {
            'purchase_date': forms.DateInput(attrs={'type': 'date'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            from apps.plm.models import Product
            from apps.sales.models import Customer, SalesOrder
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)
            self.fields['customer'].queryset = Customer.objects.filter(tenant=tenant)
            self.fields['policy'].queryset = WarrantyPolicy.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['sales_order'].queryset = SalesOrder.objects.filter(tenant=tenant)
            self.fields['sales_order'].required = False


class WarrantyClaimForm(forms.ModelForm):
    class Meta:
        model = WarrantyClaim
        fields = (
            'registration', 'rma', 'claim_date', 'resolution',
            'defect_description',
        )
        widgets = {
            'claim_date': forms.DateInput(attrs={'type': 'date'}),
            'defect_description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['registration'].queryset = WarrantyRegistration.objects.filter(
                tenant=tenant,
            )
            self.fields['rma'].queryset = RMARequest.objects.filter(tenant=tenant)
            self.fields['rma'].required = False


# ===========================================================================
# 18.5  Returns Analytics
# ===========================================================================

class FailureModeForm(forms.ModelForm):
    class Meta:
        model = FailureMode
        fields = ('name', 'category', 'description', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant

    def clean(self):
        cleaned = super().clean()
        if self._tenant and cleaned.get('name'):
            qs = FailureMode.objects.filter(
                tenant=self._tenant, name=cleaned['name'],
            ).exclude(pk=self.instance.pk or 0)
            if qs.exists():
                raise forms.ValidationError(
                    'A failure mode with this name already exists.',
                )
        return cleaned


class RootCauseCategoryForm(forms.ModelForm):
    class Meta:
        model = RootCauseCategory
        fields = ('name', 'responsible_area', 'description', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant

    def clean(self):
        cleaned = super().clean()
        if self._tenant and cleaned.get('name'):
            qs = RootCauseCategory.objects.filter(
                tenant=self._tenant, name=cleaned['name'],
            ).exclude(pk=self.instance.pk or 0)
            if qs.exists():
                raise forms.ValidationError(
                    'A root cause category with this name already exists.',
                )
        return cleaned


class ReturnAnalysisForm(forms.ModelForm):
    class Meta:
        model = ReturnAnalysis
        fields = (
            'rma_line', 'failure_mode', 'root_cause_category', 'supplier',
            'analysis_notes', 'corrective_action',
        )
        widgets = {
            'analysis_notes': forms.Textarea(attrs={'rows': 3}),
            'corrective_action': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['rma_line'].queryset = RMALine.objects.filter(tenant=tenant)
            self.fields['failure_mode'].queryset = FailureMode.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['root_cause_category'].queryset = RootCauseCategory.objects.filter(
                tenant=tenant, is_active=True,
            )
            from apps.procurement.models import Supplier
            self.fields['supplier'].queryset = Supplier.objects.filter(tenant=tenant)
            self.fields['supplier'].required = False


class SupplierChargebackForm(forms.ModelForm):
    class Meta:
        model = SupplierChargeback
        fields = ('analysis', 'supplier', 'amount', 'currency', 'reference', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['analysis'].queryset = ReturnAnalysis.objects.filter(tenant=tenant)
            from apps.procurement.models import Supplier
            self.fields['supplier'].queryset = Supplier.objects.filter(tenant=tenant)
