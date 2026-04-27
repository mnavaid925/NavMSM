"""ModelForms for Production Planning & Scheduling CRUD."""
from decimal import Decimal

from django import forms

from apps.bom.models import BillOfMaterials
from apps.plm.models import Product

from .models import (
    CapacityCalendar, DemandForecast, MasterProductionSchedule, MPSLine,
    OptimizationObjective, OptimizationRun, ProductionOrder, Routing,
    RoutingOperation, Scenario, ScenarioChange, WorkCenter,
)


def _tenant_unique_check(form, model, field, value, *, message):
    """L-01 guard — enforce (tenant, field) uniqueness at the form layer.

    Why: if `tenant` is not in `Meta.fields`, Django's default
    validate_unique() skips any unique_together set that touches it. The
    duplicate then escapes to the DB and surfaces as 1062 IntegrityError →
    HTTP 500. See .claude/tasks/lessons.md L-01.
    """
    tenant = getattr(form, '_tenant', None)
    if tenant is None or value in (None, ''):
        return
    qs = model.objects.filter(tenant=tenant, **{field: value})
    if form.instance.pk:
        qs = qs.exclude(pk=form.instance.pk)
    if qs.exists():
        form.add_error(field, message)


# ---------------- 4.1 MPS ----------------

class DemandForecastForm(forms.ModelForm):
    class Meta:
        model = DemandForecast
        fields = (
            'product', 'period_start', 'period_end',
            'forecast_qty', 'source', 'confidence_pct', 'notes',
        )
        widgets = {
            'period_start': forms.DateInput(attrs={'type': 'date'}),
            'period_end': forms.DateInput(attrs={'type': 'date'}),
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
        ps = cleaned.get('period_start')
        pe = cleaned.get('period_end')
        if ps and pe and pe < ps:
            self.add_error('period_end', 'Period end must be on or after period start.')
        return cleaned


class MasterProductionScheduleForm(forms.ModelForm):
    class Meta:
        model = MasterProductionSchedule
        fields = (
            'name', 'horizon_start', 'horizon_end', 'time_bucket', 'description',
        )
        widgets = {
            'horizon_start': forms.DateInput(attrs={'type': 'date'}),
            'horizon_end': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        hs = cleaned.get('horizon_start')
        he = cleaned.get('horizon_end')
        if hs and he and he <= hs:
            self.add_error('horizon_end', 'Horizon end must be after horizon start.')
        return cleaned


class MPSLineForm(forms.ModelForm):
    class Meta:
        model = MPSLine
        fields = (
            'product', 'period_start', 'period_end', 'forecast_qty',
            'firm_planned_qty', 'scheduled_qty', 'available_to_promise', 'notes',
        )
        widgets = {
            'period_start': forms.DateInput(attrs={'type': 'date'}),
            'period_end': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')


# ---------------- 4.2 Capacity ----------------

class WorkCenterForm(forms.ModelForm):
    class Meta:
        model = WorkCenter
        fields = (
            'code', 'name', 'work_center_type', 'capacity_per_hour',
            'efficiency_pct', 'cost_per_hour', 'description', 'is_active',
        )
        widgets = {'description': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant

    def clean(self):
        cleaned = super().clean()
        _tenant_unique_check(
            self, WorkCenter, 'code', cleaned.get('code'),
            message='A work center with this code already exists for this tenant.',
        )
        return cleaned


class CapacityCalendarForm(forms.ModelForm):
    class Meta:
        model = CapacityCalendar
        fields = ('work_center', 'day_of_week', 'shift_start', 'shift_end', 'is_working')
        widgets = {
            'shift_start': forms.TimeInput(attrs={'type': 'time'}),
            'shift_end': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['work_center'].queryset = WorkCenter.objects.filter(
                tenant=tenant, is_active=True,
            )

    def clean(self):
        cleaned = super().clean()
        s = cleaned.get('shift_start')
        e = cleaned.get('shift_end')
        if s and e and e <= s:
            self.add_error('shift_end', 'Shift end must be after shift start.')
        return cleaned


# ---------------- 4.3 Scheduling ----------------

class RoutingForm(forms.ModelForm):
    class Meta:
        model = Routing
        fields = ('name', 'product', 'version', 'is_default', 'description')
        widgets = {'description': forms.Textarea(attrs={'rows': 2})}

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
        version = cleaned.get('version')
        if self._tenant is None or product is None or not version:
            return cleaned
        qs = Routing.objects.filter(
            tenant=self._tenant, product=product, version=version,
        )
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            self.add_error(
                'version',
                f'A routing for {product.sku} version {version} already exists.',
            )
        return cleaned


class RoutingOperationForm(forms.ModelForm):
    class Meta:
        model = RoutingOperation
        fields = (
            'sequence', 'operation_name', 'work_center',
            'setup_minutes', 'run_minutes_per_unit', 'queue_minutes',
            'move_minutes', 'instructions',
        )
        widgets = {'instructions': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['work_center'].queryset = WorkCenter.objects.filter(
                tenant=tenant, is_active=True,
            )

    def clean_run_minutes_per_unit(self):
        v = self.cleaned_data['run_minutes_per_unit']
        if v < 0:
            raise forms.ValidationError('Run minutes cannot be negative.')
        return v


class ProductionOrderForm(forms.ModelForm):
    class Meta:
        model = ProductionOrder
        fields = (
            'mps_line', 'product', 'routing', 'bom', 'quantity',
            'priority', 'scheduling_method', 'requested_start', 'requested_end',
            'notes',
        )
        widgets = {
            'requested_start': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'requested_end': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')
            self.fields['routing'].queryset = Routing.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')
            self.fields['routing'].required = False
            self.fields['bom'].queryset = BillOfMaterials.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')
            self.fields['bom'].required = False
            self.fields['mps_line'].queryset = MPSLine.objects.filter(
                tenant=tenant,
            )
            self.fields['mps_line'].required = False

    def clean_quantity(self):
        v = self.cleaned_data['quantity']
        if v <= 0:
            raise forms.ValidationError('Quantity must be greater than zero.')
        return v

    def clean(self):
        cleaned = super().clean()
        rs = cleaned.get('requested_start')
        re = cleaned.get('requested_end')
        if rs and re and re <= rs:
            self.add_error(
                'requested_end',
                'Requested end must be after requested start.',
            )
        return cleaned


# ---------------- 4.4 Simulation ----------------

class ScenarioForm(forms.ModelForm):
    class Meta:
        model = Scenario
        fields = ('name', 'base_mps', 'description')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['base_mps'].queryset = MasterProductionSchedule.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')


class ScenarioChangeForm(forms.ModelForm):
    class Meta:
        model = ScenarioChange
        fields = ('change_type', 'target_ref', 'sequence', 'payload', 'notes')
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2}),
            'payload': forms.Textarea(attrs={'rows': 3, 'placeholder': '{"forecast_qty": 100}'}),
        }


# ---------------- 4.5 APO ----------------

class OptimizationObjectiveForm(forms.ModelForm):
    class Meta:
        model = OptimizationObjective
        fields = (
            'name', 'description',
            'weight_changeovers', 'weight_idle', 'weight_lateness', 'weight_priority',
            'is_default',
        )
        widgets = {'description': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant

    def clean(self):
        cleaned = super().clean()
        weights = (
            cleaned.get('weight_changeovers') or Decimal('0'),
            cleaned.get('weight_idle') or Decimal('0'),
            cleaned.get('weight_lateness') or Decimal('0'),
            cleaned.get('weight_priority') or Decimal('0'),
        )
        if all(w <= 0 for w in weights):
            raise forms.ValidationError('At least one objective weight must be greater than zero.')
        _tenant_unique_check(
            self, OptimizationObjective, 'name', cleaned.get('name'),
            message='An objective with this name already exists for this tenant.',
        )
        return cleaned


class OptimizationRunForm(forms.ModelForm):
    class Meta:
        model = OptimizationRun
        fields = ('name', 'mps', 'objective')

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['mps'].queryset = MasterProductionSchedule.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')
            self.fields['objective'].queryset = OptimizationObjective.objects.filter(
                tenant=tenant,
            )
