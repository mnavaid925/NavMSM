"""Module 16 - BI ModelForms.

Every form whose ``Meta.fields`` excludes ``tenant`` performs its own
``(tenant, ...)`` uniqueness check (Lesson L-01). Decimal fields are
validated with explicit Min/Max bounds at the model level (Lesson L-02);
forms only need to repeat checks where the underlying field is optional
or string-typed. Workflow-required reasons are captured in per-workflow
forms (Lesson L-14). ``ReportExportForm.clean_file`` enforces the upload
allowlist + 25 MB cap (Lesson L-22).
"""
from __future__ import annotations

import os
from decimal import Decimal

from django import forms
from django.utils.text import slugify

from . import models


ALLOWED_EXPORT_EXTENSIONS = {'.csv', '.xlsx', '.pdf', '.html'}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


class _TenantScopedFormMixin:
    """Stashes the tenant in ``__init__`` so ``clean()`` can dedupe."""

    def __init__(self, *args, **kwargs):
        self._tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)


# ---------------------------------------------------------------------------
# 16.1  KPI forms
# ---------------------------------------------------------------------------

class KPIDefinitionForm(_TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.KPIDefinition
        fields = [
            'code', 'name', 'description', 'unit', 'direction',
            'target_value', 'warning_threshold', 'critical_threshold',
            'is_active',
        ]

    def clean_code(self):
        code = self.cleaned_data.get('code')
        if not code or not self._tenant:
            return code
        qs = models.KPIDefinition.all_objects.filter(tenant=self._tenant, code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'A KPI with code "{code}" already exists for this tenant.')
        return code


class KPIDashboardForm(_TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.KPIDashboard
        fields = [
            'name', 'slug', 'description', 'owner', 'is_shared',
            'default_period', 'auto_refresh_minutes',
        ]

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get('name', '')
        slug = cleaned.get('slug', '') or slugify(name)
        cleaned['slug'] = slug
        if self._tenant and slug:
            qs = models.KPIDashboard.all_objects.filter(tenant=self._tenant, slug=slug)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('slug', f'A dashboard with slug "{slug}" already exists.')
        return cleaned


class KPIWidgetForm(_TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.KPIWidget
        fields = [
            'dashboard', 'kpi_definition', 'position', 'chart_type',
            'scope_filter', 'compare_to_previous', 'title_override',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['dashboard'].queryset = models.KPIDashboard.all_objects.filter(tenant=self._tenant)
            self.fields['kpi_definition'].queryset = (
                models.KPIDefinition.all_objects.filter(tenant=self._tenant, is_active=True)
            )


# ---------------------------------------------------------------------------
# 16.2  Report forms
# ---------------------------------------------------------------------------

class ReportDataSourceForm(_TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.ReportDataSource
        fields = ['code', 'name', 'description', 'model_label', 'allowed_fields', 'default_filters', 'is_active']

    def clean_code(self):
        code = self.cleaned_data.get('code')
        if not code or not self._tenant:
            return code
        from .services.registry import REGISTERED_SOURCES
        if code not in REGISTERED_SOURCES:
            raise forms.ValidationError(
                f'Code "{code}" is not in the static REGISTERED_SOURCES whitelist. '
                f'Add it in services/registry.py first.'
            )
        qs = models.ReportDataSource.all_objects.filter(tenant=self._tenant, code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'A data source with code "{code}" already exists for this tenant.')
        return code


class ReportDefinitionForm(_TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.ReportDefinition
        fields = [
            'name', 'description', 'data_source', 'is_shared',
            'group_by_field', 'sort_field', 'sort_direction', 'row_limit',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['data_source'].queryset = (
                models.ReportDataSource.all_objects.filter(tenant=self._tenant, is_active=True)
            )

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if not name or not self._tenant:
            return name
        qs = models.ReportDefinition.all_objects.filter(tenant=self._tenant, name=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'A report named "{name}" already exists.')
        return name


class ReportFieldForm(_TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.ReportField
        fields = ['report', 'field_name', 'display_name', 'aggregation', 'position']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['report'].queryset = models.ReportDefinition.all_objects.filter(tenant=self._tenant)


class ReportFilterForm(_TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.ReportFilter
        fields = ['report', 'field_name', 'operator', 'value', 'value_to', 'position']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['report'].queryset = models.ReportDefinition.all_objects.filter(tenant=self._tenant)

    def clean(self):
        cleaned = super().clean()
        op = cleaned.get('operator')
        if op == 'between' and not cleaned.get('value_to'):
            self.add_error('value_to', 'value_to is required for "between" operator.')
        return cleaned


# ---------------------------------------------------------------------------
# 16.3  Predictive forms
# ---------------------------------------------------------------------------

class PredictiveModelForm(_TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.PredictiveModel
        fields = [
            'code', 'name', 'description', 'target_model_label',
            'lookback_days', 'forecast_horizon_days', 'parameters', 'is_active',
        ]

    def clean(self):
        cleaned = super().clean()
        code = cleaned.get('code')
        name = cleaned.get('name')
        if self._tenant and code and name:
            qs = models.PredictiveModel.all_objects.filter(tenant=self._tenant, code=code, name=name)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('name', f'A predictive model "{code}/{name}" already exists.')
        return cleaned


class PredictionRunCancelForm(forms.Form):
    """L-14: cancelling a queued/running prediction requires a reason."""

    cancellation_reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=True, max_length=2000,
    )

    def clean_cancellation_reason(self):
        v = (self.cleaned_data.get('cancellation_reason') or '').strip()
        if not v:
            raise forms.ValidationError('Cancellation reason is required.')
        return v


# ---------------------------------------------------------------------------
# 16.4  Data Warehouse forms
# ---------------------------------------------------------------------------

class DataMartForm(_TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.DataMart
        fields = [
            'code', 'name', 'description', 'source_definition',
            'refresh_frequency', 'row_level_security_field', 'is_active',
        ]

    def clean_code(self):
        code = self.cleaned_data.get('code')
        if not code or not self._tenant:
            return code
        qs = models.DataMart.all_objects.filter(tenant=self._tenant, code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'A data mart with code "{code}" already exists.')
        return code

    def clean_source_definition(self):
        sd = self.cleaned_data.get('source_definition') or {}
        if not isinstance(sd, dict):
            raise forms.ValidationError('source_definition must be a JSON object.')
        if 'model_label' not in sd:
            raise forms.ValidationError('source_definition must include a "model_label" key.')
        return sd


class DataMartColumnForm(_TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.DataMartColumn
        fields = [
            'data_mart', 'code', 'display_name', 'data_type',
            'is_dimension', 'is_measure', 'aggregation_hint', 'position',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['data_mart'].queryset = models.DataMart.all_objects.filter(tenant=self._tenant)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('is_dimension') and cleaned.get('is_measure'):
            self.add_error('is_measure', 'A column cannot be both a dimension and a measure.')
        if self._tenant:
            mart = cleaned.get('data_mart')
            code = cleaned.get('code')
            if mart and code:
                qs = models.DataMartColumn.all_objects.filter(tenant=self._tenant, data_mart=mart, code=code)
                if self.instance and self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.exists():
                    self.add_error('code', f'Column "{code}" already exists on this mart.')
        return cleaned


# ---------------------------------------------------------------------------
# 16.5  Distribution forms
# ---------------------------------------------------------------------------

class ReportScheduleForm(_TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.ReportSchedule
        fields = [
            'name', 'description', 'report', 'dashboard',
            'frequency', 'cron_expression', 'timezone_name',
            'next_run_at', 'format',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['report'].queryset = models.ReportDefinition.all_objects.filter(tenant=self._tenant)
            self.fields['dashboard'].queryset = models.KPIDashboard.all_objects.filter(tenant=self._tenant)
        self.fields['report'].required = False
        self.fields['dashboard'].required = False
        self.fields['cron_expression'].required = False

    def clean(self):
        cleaned = super().clean()
        report = cleaned.get('report')
        dashboard = cleaned.get('dashboard')
        if bool(report) == bool(dashboard):
            raise forms.ValidationError('Exactly one of report or dashboard must be selected.')

        name = cleaned.get('name')
        if self._tenant and name:
            qs = models.ReportSchedule.all_objects.filter(tenant=self._tenant, name=name)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('name', f'A schedule named "{name}" already exists.')

        if cleaned.get('frequency') == 'custom' and not cleaned.get('cron_expression', '').strip():
            self.add_error('cron_expression', 'A cron expression is required when frequency is "custom".')
        return cleaned


class ReportScheduleDisableForm(forms.Form):
    """L-14: disabling a schedule requires an explanatory reason."""

    disabled_reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=True, max_length=2000,
    )

    def clean_disabled_reason(self):
        v = (self.cleaned_data.get('disabled_reason') or '').strip()
        if not v:
            raise forms.ValidationError('Reason is required to disable a schedule.')
        return v


class ReportRecipientForm(_TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = models.ReportRecipient
        fields = ['schedule', 'name', 'email', 'user', 'notify_on_failure', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['schedule'].queryset = models.ReportSchedule.all_objects.filter(tenant=self._tenant)

    def clean(self):
        cleaned = super().clean()
        schedule = cleaned.get('schedule')
        email = cleaned.get('email')
        if self._tenant and schedule and email:
            qs = models.ReportRecipient.all_objects.filter(
                tenant=self._tenant, schedule=schedule, email=email,
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('email', 'This recipient is already on the schedule.')
        return cleaned


class ReportExportForm(_TenantScopedFormMixin, forms.ModelForm):
    """L-22: file upload allowlist + size cap. Generally exports are server-
    generated, so this form is only used when an admin manually uploads
    a pre-rendered artifact."""

    class Meta:
        model = models.ReportExport
        fields = ['report', 'dashboard', 'format', 'file', 'row_count']

    def clean_file(self):
        f = self.cleaned_data.get('file')
        if not f:
            return f
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in ALLOWED_EXPORT_EXTENSIONS:
            raise forms.ValidationError(
                f'File type "{ext}" is not allowed. Allowed: {", ".join(sorted(ALLOWED_EXPORT_EXTENSIONS))}.'
            )
        if f.size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError(
                f'File too large ({f.size} bytes). Limit: {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.'
            )
        return f
