"""ModelForms for Module 10 - Equipment & Asset Management.

Per Lesson L-01, every form whose ``Meta.fields`` excludes ``tenant`` performs
its own duplicate check inside ``clean()``. Per Lesson L-14, per-workflow
required fields are enforced by dedicated *WorkflowForm classes.
"""
from decimal import Decimal

from django import forms

from apps.plm.models import Product

from . import models


class TenantScopedFormMixin:
    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant


# ============================================================================
# 10.1  Asset Registry
# ============================================================================

class AssetCategoryForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.AssetCategory
        fields = ('name', 'parent', 'description', 'is_active')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            qs = models.AssetCategory.all_objects.filter(tenant=self._tenant)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            self.fields['parent'].queryset = qs
            self.fields['parent'].required = False

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get('name')
        parent = cleaned.get('parent')
        if self._tenant and name:
            qs = models.AssetCategory.all_objects.filter(
                tenant=self._tenant, name=name, parent=parent,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('name', 'A category with this name already exists at the same level.')
        return cleaned


class AssetForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.Asset
        fields = (
            'name', 'description', 'category', 'parent', 'warehouse', 'location_detail',
            'manufacturer', 'model_number', 'serial_number',
            'installation_date', 'commissioning_date',
            'criticality', 'status', 'purchase_cost', 'current_value',
            'warranty_expiry', 'is_active', 'notes',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
            'installation_date': forms.DateInput(attrs={'type': 'date'}),
            'commissioning_date': forms.DateInput(attrs={'type': 'date'}),
            'warranty_expiry': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            from apps.inventory.models import Warehouse
            self.fields['category'].queryset = models.AssetCategory.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )
            self.fields['category'].required = False
            parent_qs = models.Asset.all_objects.filter(tenant=self._tenant)
            if self.instance.pk:
                parent_qs = parent_qs.exclude(pk=self.instance.pk)
            self.fields['parent'].queryset = parent_qs
            self.fields['parent'].required = False
            self.fields['warehouse'].queryset = Warehouse.all_objects.filter(tenant=self._tenant)
            self.fields['warehouse'].required = False

    def clean(self):
        cleaned = super().clean()
        # Asset.tag is auto-generated; nothing to dedupe at form level.
        commission = cleaned.get('commissioning_date')
        install = cleaned.get('installation_date')
        if commission and install and commission < install:
            self.add_error('commissioning_date',
                           'Commissioning date cannot be before installation date.')
        return cleaned


class AssetSparePartForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.AssetSparePart
        fields = ('product', 'recommended_min_qty', 'quantity_on_hand', 'notes')

    def __init__(self, *args, asset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._asset = asset
        if self._tenant is not None:
            self.fields['product'].queryset = Product.all_objects.filter(
                tenant=self._tenant,
            ).exclude(status='obsolete')

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get('product')
        if self._asset and product:
            qs = models.AssetSparePart.all_objects.filter(
                asset=self._asset, product=product,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('product', 'This product is already linked to the asset.')
        return cleaned


class AssetMeterReadingForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.AssetMeterReading
        fields = ('meter_type', 'reading_value', 'recorded_at', 'notes')
        widgets = {
            'recorded_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class AssetDocumentForm(TenantScopedFormMixin, forms.ModelForm):
    ALLOWED_EXT = {'.pdf', '.png', '.jpg', '.jpeg', '.dwg', '.dxf'}
    MAX_BYTES = 25 * 1024 * 1024

    class Meta:
        model = models.AssetDocument
        fields = ('name', 'doc_type', 'attachment', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

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


# ============================================================================
# 10.2  Preventive Maintenance
# ============================================================================

class MaintenancePlanForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.MaintenancePlan
        fields = (
            'name', 'description', 'asset', 'trigger_type',
            'frequency_days', 'frequency_meter', 'meter_type',
            'next_due_at', 'next_due_meter', 'is_active',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'next_due_at': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['asset'].queryset = models.Asset.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )

    def clean(self):
        cleaned = super().clean()
        trigger = cleaned.get('trigger_type')
        if trigger in ('calendar', 'both') and not cleaned.get('frequency_days'):
            self.add_error('frequency_days', 'Required for calendar / both triggers.')
        if trigger in ('meter', 'both') and not cleaned.get('frequency_meter'):
            self.add_error('frequency_meter', 'Required for meter / both triggers.')
        if trigger in ('meter', 'both') and not cleaned.get('meter_type'):
            self.add_error('meter_type', 'Required for meter / both triggers.')
        # L-01 manual unique_together check (tenant, asset, name).
        asset = cleaned.get('asset')
        name = cleaned.get('name')
        if self._tenant and asset and name:
            qs = models.MaintenancePlan.all_objects.filter(
                tenant=self._tenant, asset=asset, name=name,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('name', 'A plan with this name already exists for this asset.')
        return cleaned


class MaintenanceTaskForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.MaintenanceTask
        fields = ('sequence', 'description', 'instructions', 'expected_minutes', 'is_critical')
        widgets = {'instructions': forms.Textarea(attrs={'rows': 2})}


class PMScheduleForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.PMSchedule
        fields = ('plan', 'scheduled_date', 'scheduled_meter', 'assignee', 'notes')
        widgets = {
            'scheduled_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['plan'].queryset = models.MaintenancePlan.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )


class PMScheduleCompleteForm(forms.Form):
    """Per Lesson L-14, completion requires at least one task result."""

    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)

    def __init__(self, *args, schedule=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._schedule = schedule

    def clean(self):
        cleaned = super().clean()
        if self._schedule is not None:
            existing = models.PMTaskCompletion.all_objects.filter(
                pm_schedule=self._schedule,
            ).count()
            plan_tasks = models.MaintenanceTask.all_objects.filter(
                plan=self._schedule.plan,
            ).count()
            if plan_tasks and existing == 0:
                raise forms.ValidationError(
                    'Record at least one task completion before completing this PM.'
                )
        return cleaned


class PMTaskCompletionForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.PMTaskCompletion
        fields = ('task', 'result', 'comments')
        widgets = {'comments': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, schedule=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._schedule = schedule
        if schedule is not None:
            self.fields['task'].queryset = models.MaintenanceTask.all_objects.filter(
                plan=schedule.plan,
            )


# ============================================================================
# 10.3  Predictive Maintenance
# ============================================================================

class ConditionMonitoringPointForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.ConditionMonitoringPoint
        fields = (
            'asset', 'name', 'parameter', 'unit',
            'low_alarm', 'high_alarm', 'is_active', 'notes',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['asset'].queryset = models.Asset.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )

    def clean(self):
        cleaned = super().clean()
        asset = cleaned.get('asset')
        name = cleaned.get('name')
        if self._tenant and asset and name:
            qs = models.ConditionMonitoringPoint.all_objects.filter(
                tenant=self._tenant, asset=asset, name=name,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('name', 'A monitoring point with this name already exists for this asset.')
        low = cleaned.get('low_alarm')
        high = cleaned.get('high_alarm')
        if low is not None and high is not None and low >= high:
            self.add_error('high_alarm', 'High alarm must be greater than low alarm.')
        return cleaned


class ConditionReadingForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.ConditionReading
        fields = ('point', 'reading_value', 'recorded_at', 'notes')
        widgets = {'recorded_at': forms.DateTimeInput(attrs={'type': 'datetime-local'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['point'].queryset = models.ConditionMonitoringPoint.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )


class FailurePredictionResolveForm(forms.Form):
    """Per Lesson L-14, resolving a prediction requires non-empty notes."""

    OUTCOME_CHOICES = [
        ('resolved', 'Resolved (truly a defect / fixed)'),
        ('false_positive', 'False Positive (no actual issue)'),
    ]

    outcome = forms.ChoiceField(choices=OUTCOME_CHOICES)
    resolution_notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}), required=True,
    )

    def clean_resolution_notes(self):
        notes = (self.cleaned_data.get('resolution_notes') or '').strip()
        if not notes:
            raise forms.ValidationError('Resolution notes are required for traceability.')
        return notes


# ============================================================================
# 10.4  Maintenance Work Orders
# ============================================================================

class MaintenanceWorkOrderForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.MaintenanceWorkOrder
        fields = (
            'asset', 'wo_type', 'priority', 'title', 'problem_description',
            'assigned_to', 'scheduled_start', 'failure_code',
            'source_pm_schedule', 'source_failure_prediction', 'source_andon',
        )
        widgets = {
            'problem_description': forms.Textarea(attrs={'rows': 3}),
            'scheduled_start': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['asset'].queryset = models.Asset.all_objects.filter(
                tenant=self._tenant, is_active=True,
            )
            self.fields['source_pm_schedule'].queryset = models.PMSchedule.all_objects.filter(
                tenant=self._tenant,
            )
            self.fields['source_pm_schedule'].required = False
            self.fields['source_failure_prediction'].queryset = models.FailurePrediction.all_objects.filter(
                tenant=self._tenant,
            )
            self.fields['source_failure_prediction'].required = False
            from apps.mes.models import AndonAlert
            self.fields['source_andon'].queryset = AndonAlert.all_objects.filter(
                tenant=self._tenant,
            )
            self.fields['source_andon'].required = False


class MWOCompleteForm(forms.Form):
    """Per Lesson L-14, completing an MWO requires non-empty resolution notes."""

    resolution_notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}))
    root_cause = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}), required=False,
    )

    def clean_resolution_notes(self):
        notes = (self.cleaned_data.get('resolution_notes') or '').strip()
        if not notes:
            raise forms.ValidationError(
                'Resolution notes are required to complete a work order.'
            )
        return notes


class MWOLaborLogForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.MWOLaborLog
        fields = ('technician', 'started_at', 'ended_at', 'hourly_rate', 'notes')
        widgets = {
            'started_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'ended_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def clean(self):
        cleaned = super().clean()
        s = cleaned.get('started_at')
        e = cleaned.get('ended_at')
        if s and e and e < s:
            self.add_error('ended_at', 'End time cannot be before start time.')
        return cleaned


class MWOMaterialLogForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.MWOMaterialLog
        fields = ('product', 'quantity', 'unit_of_measure', 'unit_cost', 'notes')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['product'].queryset = Product.all_objects.filter(
                tenant=self._tenant,
            ).exclude(status='obsolete')


class DowntimeEventForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.DowntimeEvent
        fields = ('asset', 'mwo', 'started_at', 'ended_at', 'downtime_type', 'reason', 'notes')
        widgets = {
            'started_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'ended_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            self.fields['asset'].queryset = models.Asset.all_objects.filter(
                tenant=self._tenant,
            )
            self.fields['mwo'].queryset = models.MaintenanceWorkOrder.all_objects.filter(
                tenant=self._tenant,
            )
            self.fields['mwo'].required = False

    def clean(self):
        cleaned = super().clean()
        s = cleaned.get('started_at')
        e = cleaned.get('ended_at')
        if s and e and e < s:
            self.add_error('ended_at', 'End time cannot be before start time.')
        return cleaned


# ============================================================================
# 10.5  Tools & Dies
# ============================================================================

class ToolForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.Tool
        fields = (
            'name', 'description', 'tool_type', 'category', 'location', 'status',
            'purchase_date', 'purchase_cost',
            'expected_life_cycles', 'expected_life_hours',
            'last_sharpened_at', 'next_sharpen_due',
            'cavity_count', 'is_active', 'notes',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
            'purchase_date': forms.DateInput(attrs={'type': 'date'}),
            'last_sharpened_at': forms.DateInput(attrs={'type': 'date'}),
            'next_sharpen_due': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned = super().clean()
        tool_type = cleaned.get('tool_type')
        cav = cleaned.get('cavity_count') or 0
        if tool_type != 'mold' and cav and cav > 0:
            self.add_error('cavity_count',
                           'Cavity count is only meaningful for mold-type tools.')
        if tool_type == 'mold' and not cav:
            self.add_error('cavity_count',
                           'Mold tools require a cavity count of at least 1.')
        return cleaned


class ToolUsageLogForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.ToolUsageLog
        fields = ('mes_work_order', 'used_at', 'cycles_added', 'hours_added', 'notes')
        widgets = {'used_at': forms.DateTimeInput(attrs={'type': 'datetime-local'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant is not None:
            from apps.mes.models import MESWorkOrder
            self.fields['mes_work_order'].queryset = MESWorkOrder.all_objects.filter(
                tenant=self._tenant,
            )
            self.fields['mes_work_order'].required = False


class ToolMaintenanceRecordForm(TenantScopedFormMixin, forms.ModelForm):
    ALLOWED_EXT = {'.pdf', '.png', '.jpg', '.jpeg'}
    MAX_BYTES = 25 * 1024 * 1024

    class Meta:
        model = models.ToolMaintenanceRecord
        fields = ('record_type', 'performed_at', 'cost', 'notes', 'attachment')
        widgets = {
            'performed_at': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

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


class MoldCavityHistoryForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.MoldCavityHistory
        fields = ('cavity_number', 'cycles', 'last_inspected_at',
                  'defect_count', 'status', 'notes')
        widgets = {'last_inspected_at': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, tool=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tool = tool

    def clean(self):
        cleaned = super().clean()
        cav = cleaned.get('cavity_number')
        if self._tool and self._tool.tool_type != 'mold':
            raise forms.ValidationError(
                'Cavity history can only be recorded for mold-type tools.'
            )
        if self._tool and cav and self._tool.cavity_count and cav > self._tool.cavity_count:
            self.add_error('cavity_number',
                           f'Cavity number exceeds the tool cavity count ({self._tool.cavity_count}).')
        if self._tool and cav:
            qs = models.MoldCavityHistory.all_objects.filter(
                tool=self._tool, cavity_number=cav,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('cavity_number', 'A history entry already exists for this cavity.')
        return cleaned
