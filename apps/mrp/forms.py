"""ModelForms for Material Requirements Planning CRUD.

Per Lesson L-01, every form whose Meta.fields excludes ``tenant`` performs
its own duplicate check inside ``clean()`` — Django's default
``validate_unique`` cannot enforce a ``unique_together`` set that touches a
field not present in ``cleaned_data``.
"""
from decimal import Decimal

from django import forms

from apps.bom.models import BillOfMaterials
from apps.plm.models import Product
from apps.pps.models import MasterProductionSchedule

from .models import (
    ForecastModel, ForecastRun, InventorySnapshot, MRPCalculation, MRPException,
    MRPPurchaseRequisition, MRPRun, ScheduledReceipt, SeasonalityProfile,
)


# ---------------- 5.1  Demand Forecasting ----------------

class ForecastModelForm(forms.ModelForm):
    class Meta:
        model = ForecastModel
        fields = (
            'name', 'description', 'method', 'params',
            'period_type', 'horizon_periods', 'is_active',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'params': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': '{"window": 3} or {"alpha": 0.3} or {"weights": [0.2,0.3,0.5]}',
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get('name')
        if self._tenant and name:
            qs = ForecastModel.all_objects.filter(tenant=self._tenant, name=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('name', 'A forecast model with this name already exists.')
        return cleaned


class SeasonalityProfileForm(forms.ModelForm):
    class Meta:
        model = SeasonalityProfile
        fields = ('product', 'period_type', 'period_index', 'seasonal_index', 'notes')

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get('product')
        period_type = cleaned.get('period_type')
        period_index = cleaned.get('period_index')
        if period_type == 'month' and period_index and period_index > 12:
            self.add_error('period_index', 'Monthly index must be 1–12.')
        # F-13 (D-14): weekly indices must be 1-52; the model validator catches
        # values > 52 but the resulting error is field-level rather than the
        # friendly form-level message. Mirror the monthly check here.
        if period_type == 'week' and period_index and period_index > 52:
            self.add_error('period_index', 'Weekly index must be 1–52.')
        if self._tenant and product and period_type and period_index:
            qs = SeasonalityProfile.all_objects.filter(
                tenant=self._tenant, product=product,
                period_type=period_type, period_index=period_index,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    'This product already has a seasonality entry for this period.'
                )
        return cleaned


class ForecastRunForm(forms.ModelForm):
    class Meta:
        model = ForecastRun
        fields = ('forecast_model', 'run_date', 'notes')
        widgets = {
            'run_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['forecast_model'].queryset = ForecastModel.objects.filter(
                tenant=tenant, is_active=True,
            )


# ---------------- 5.2  Net Requirements ----------------

class InventorySnapshotForm(forms.ModelForm):
    class Meta:
        model = InventorySnapshot
        fields = (
            'product', 'on_hand_qty', 'safety_stock', 'reorder_point',
            'lead_time_days', 'lot_size_method', 'lot_size_value', 'lot_size_max',
            'as_of_date', 'notes',
        )
        widgets = {
            'as_of_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get('lot_size_method')
        val = cleaned.get('lot_size_value') or Decimal('0')
        mx = cleaned.get('lot_size_max') or Decimal('0')
        product = cleaned.get('product')
        if method == 'foq' and val <= 0:
            self.add_error('lot_size_value', 'FOQ size must be greater than zero.')
        if method == 'poq' and val <= 0:
            self.add_error('lot_size_value', 'POQ period count must be at least 1.')
        if method == 'min_max':
            if val <= 0:
                self.add_error('lot_size_value', 'Min-Max minimum must be greater than zero.')
            if mx <= val:
                self.add_error('lot_size_max', 'Max must be greater than Min.')
        # Manual unique check on (tenant, product) — OneToOneField + tenant scoping.
        if self._tenant and product:
            qs = InventorySnapshot.all_objects.filter(tenant=self._tenant, product=product)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('product', 'This product already has an inventory snapshot.')
        return cleaned


class ScheduledReceiptForm(forms.ModelForm):
    class Meta:
        model = ScheduledReceipt
        fields = ('product', 'receipt_type', 'quantity', 'expected_date', 'reference', 'notes')
        widgets = {
            'expected_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')


class MRPCalculationForm(forms.ModelForm):
    class Meta:
        model = MRPCalculation
        fields = ('name', 'horizon_start', 'horizon_end', 'time_bucket', 'source_mps', 'description')
        widgets = {
            'horizon_start': forms.DateInput(attrs={'type': 'date'}),
            'horizon_end': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['source_mps'].queryset = MasterProductionSchedule.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')
            self.fields['source_mps'].required = False

    def clean(self):
        cleaned = super().clean()
        hs = cleaned.get('horizon_start')
        he = cleaned.get('horizon_end')
        if hs and he and he <= hs:
            self.add_error('horizon_end', 'Horizon end must be after horizon start.')
        return cleaned


# ---------------- 5.3  Purchase Requisitions ----------------

class MRPPurchaseRequisitionForm(forms.ModelForm):
    class Meta:
        model = MRPPurchaseRequisition
        fields = (
            'product', 'quantity', 'required_by_date', 'suggested_release_date',
            'priority', 'notes',
        )
        widgets = {
            'required_by_date': forms.DateInput(attrs={'type': 'date'}),
            'suggested_release_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')

    def clean(self):
        cleaned = super().clean()
        rb = cleaned.get('required_by_date')
        sr = cleaned.get('suggested_release_date')
        if rb and sr and sr > rb:
            self.add_error('suggested_release_date', 'Release date cannot be after required-by date.')
        return cleaned


# ---------------- 5.4  Exceptions ----------------

class MRPExceptionResolveForm(forms.ModelForm):
    class Meta:
        model = MRPException
        fields = ('resolution_notes',)
        widgets = {'resolution_notes': forms.Textarea(attrs={'rows': 3})}

    def clean_resolution_notes(self):
        # F-12 (D-06): resolution_notes is optional on the model so the engine
        # can synthesise exception rows without requiring a note. But operators
        # closing an exception via the resolve flow MUST justify the closure
        # for the audit trail.
        notes = (self.cleaned_data.get('resolution_notes') or '').strip()
        if not notes:
            raise forms.ValidationError('Please add a resolution note.')
        return notes


# ---------------- 5.5  MRP Run ----------------

class MRPRunForm(forms.ModelForm):
    class Meta:
        model = MRPRun
        fields = ('name', 'run_type', 'source_mps', 'commit_notes')
        widgets = {'commit_notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['source_mps'].queryset = MasterProductionSchedule.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')
            self.fields['source_mps'].required = False
