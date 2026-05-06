"""Module 12 - Cost Management & Accounting ModelForms.

Honors:
    - Lesson L-01: forms whose Meta.fields excludes ``tenant`` enforce their
      own ``(tenant, ...)`` unique_together via clean().
    - Lesson L-02: every Decimal field carries explicit MinValueValidator
      (declared on the model; ModelForm picks them up).
    - Lesson L-14: per-workflow forms enforce per-transition required fields.
"""
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from . import models


class TenantForm(forms.ModelForm):
    """Stash request.tenant on self._tenant for clean() use (Lesson L-01)."""

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant


# ============================================================================
# 12.1  Standard Costing
# ============================================================================

class StandardCostVersionForm(TenantForm):
    class Meta:
        model = models.StandardCostVersion
        fields = ['name', 'effective_from', 'effective_to', 'notes']
        widgets = {
            'effective_from': forms.DateInput(attrs={'type': 'date'}),
            'effective_to': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        data = super().clean()
        eff_from = data.get('effective_from')
        eff_to = data.get('effective_to')
        if eff_from and eff_to and eff_to < eff_from:
            self.add_error('effective_to', 'Must be on or after Effective From.')
        return data


class StandardCostVersionApproveForm(forms.Form):
    """L-14: approval requires non-empty notes."""

    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=True)

    def clean_notes(self):
        notes = self.cleaned_data.get('notes', '').strip()
        if not notes:
            raise ValidationError('Approval notes are required.')
        return notes


class StandardCostForm(TenantForm):
    class Meta:
        model = models.StandardCost
        fields = [
            'product', 'material_cost', 'labor_cost', 'overhead_cost',
            'tooling_cost', 'subassembly_cost', 'source', 'currency',
        ]

    def __init__(self, *args, version=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._version = version

    def clean(self):
        data = super().clean()
        version = self._version or (self.instance.version_id and self.instance.version)
        product = data.get('product')
        if version and product:
            qs = models.StandardCost.all_objects.filter(version=version, product=product)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('product', 'A standard cost row for this product already exists in this version.')
        return data


# ============================================================================
# 12.4  Overhead Allocation
# ============================================================================

class CostDriverForm(TenantForm):
    class Meta:
        model = models.CostDriver
        fields = ['name', 'code', 'unit_of_measure', 'description', 'is_active']

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.CostDriver.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A driver with this code already exists.')
        return data


class OverheadPoolForm(TenantForm):
    class Meta:
        model = models.OverheadPool
        fields = [
            'name', 'code', 'pool_type', 'default_driver',
            'allocation_method', 'description', 'is_active',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['default_driver'].queryset = (
                models.CostDriver.all_objects.filter(tenant=self._tenant, is_active=True)
            )

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        code = data.get('code')
        if code:
            qs = models.OverheadPool.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A pool with this code already exists.')
        return data


class OverheadRateForm(TenantForm):
    class Meta:
        model = models.OverheadRate
        fields = [
            'pool', 'period', 'driver',
            'budgeted_amount', 'budgeted_driver_qty', 'is_active', 'notes',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['pool'].queryset = (
                models.OverheadPool.all_objects.filter(tenant=self._tenant, is_active=True)
            )
            self.fields['period'].queryset = (
                models.AccountingPeriod.all_objects.filter(tenant=self._tenant)
            )
            self.fields['driver'].queryset = (
                models.CostDriver.all_objects.filter(tenant=self._tenant, is_active=True)
            )

    def clean(self):
        data = super().clean()
        pool = data.get('pool')
        period = data.get('period')
        if pool and period:
            qs = models.OverheadRate.all_objects.filter(pool=pool, period=period)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('pool', 'A rate for this pool + period already exists.')
        return data


class DriverActualsForm(TenantForm):
    class Meta:
        model = models.DriverActuals
        fields = [
            'driver', 'period', 'cost_center', 'production_order',
            'quantity', 'notes',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            from apps.labor.models import CostCenter
            from apps.pps.models import ProductionOrder

            self.fields['driver'].queryset = (
                models.CostDriver.all_objects.filter(tenant=self._tenant, is_active=True)
            )
            self.fields['period'].queryset = (
                models.AccountingPeriod.all_objects.filter(tenant=self._tenant)
            )
            self.fields['cost_center'].queryset = (
                CostCenter.all_objects.filter(tenant=self._tenant, is_active=True)
            )
            self.fields['production_order'].queryset = (
                ProductionOrder.all_objects.filter(tenant=self._tenant)
            )

    def clean(self):
        data = super().clean()
        cc = data.get('cost_center')
        po = data.get('production_order')
        if cc is None and po is None:
            raise ValidationError(
                'Either Cost Center or Production Order must be set.'
            )
        if cc is not None and po is not None:
            raise ValidationError(
                'Only one of Cost Center / Production Order may be set.'
            )
        return data


class OverheadApplyForm(forms.Form):
    period = forms.ModelChoiceField(queryset=models.AccountingPeriod.objects.none())

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['period'].queryset = models.AccountingPeriod.all_objects.filter(
                tenant=tenant, status='open',
            )


class OverheadReverseForm(forms.Form):
    """L-14: reversal requires non-empty reason."""

    reversal_reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}), required=True,
    )

    def clean_reversal_reason(self):
        reason = self.cleaned_data.get('reversal_reason', '').strip()
        if not reason:
            raise ValidationError('Reversal reason is required.')
        return reason


# ============================================================================
# 12.5  Periods
# ============================================================================

class AccountingPeriodForm(TenantForm):
    class Meta:
        model = models.AccountingPeriod
        fields = ['name', 'period_type', 'start_date', 'end_date', 'notes']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        data = super().clean()
        if not self._tenant:
            return data
        s = data.get('start_date')
        e = data.get('end_date')
        if s and e:
            if e < s:
                self.add_error('end_date', 'Must be on or after Start Date.')
            qs = models.AccountingPeriod.all_objects.filter(
                tenant=self._tenant, start_date=s, end_date=e,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('start_date', 'A period with this date range already exists.')
        return data


class AccountingPeriodLockForm(forms.Form):
    """L-14: lock requires confirmation when there are unanalyzed variances."""

    confirm = forms.BooleanField(required=True)
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}), required=False,
    )


# ============================================================================
# 12.3  WIP / Job Cost
# ============================================================================

class WIPEntryForm(TenantForm):
    class Meta:
        model = models.WIPEntry
        fields = [
            'job', 'entry_type', 'amount', 'quantity', 'unit_of_measure',
            'cost_center', 'routing_operation', 'notes',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            from apps.labor.models import CostCenter
            from apps.pps.models import RoutingOperation

            self.fields['job'].queryset = models.JobCost.all_objects.filter(tenant=self._tenant)
            self.fields['cost_center'].queryset = CostCenter.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )
            self.fields['routing_operation'].queryset = RoutingOperation.all_objects.filter(
                tenant=self._tenant,
            )


class JobCostForm(TenantForm):
    class Meta:
        model = models.JobCost
        fields = ['production_order', 'notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            from apps.pps.models import ProductionOrder
            self.fields['production_order'].queryset = ProductionOrder.all_objects.filter(
                tenant=self._tenant,
            )


class JobCloseForm(forms.Form):
    """Confirm closing of a job. ``force`` allows non-zero balance closure."""

    force = forms.BooleanField(required=False)
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}), required=False,
    )


# ============================================================================
# 12.2  Variance
# ============================================================================

class CostVarianceForm(TenantForm):
    class Meta:
        model = models.CostVariance
        fields = [
            'production_order', 'version', 'analysis_notes',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            from apps.pps.models import ProductionOrder
            self.fields['production_order'].queryset = ProductionOrder.all_objects.filter(
                tenant=self._tenant,
            )
            self.fields['version'].queryset = models.StandardCostVersion.all_objects.filter(
                tenant=self._tenant,
            )

    def clean(self):
        data = super().clean()
        po = data.get('production_order')
        v = data.get('version')
        if po and v:
            qs = models.CostVariance.all_objects.filter(production_order=po, version=v)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('version', 'A variance for this PO + version already exists.')
        return data


# ============================================================================
# 12.5  P&L manual inputs
# ============================================================================

class PlantPnLForm(forms.Form):
    period = forms.ModelChoiceField(queryset=models.AccountingPeriod.objects.none())
    selling_expense = forms.DecimalField(
        max_digits=16, decimal_places=2, min_value=Decimal('0'), initial=Decimal('0'),
    )
    general_admin_expense = forms.DecimalField(
        max_digits=16, decimal_places=2, min_value=Decimal('0'), initial=Decimal('0'),
    )
    unallocated_overhead = forms.DecimalField(
        max_digits=16, decimal_places=2, initial=Decimal('0'),
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['period'].queryset = models.AccountingPeriod.all_objects.filter(
                tenant=tenant,
            )
