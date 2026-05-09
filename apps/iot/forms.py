"""ModelForms for Module 15 - IoT & SCADA Integration.

Lessons applied:
    * L-01 unique_together with tenant excluded -> explicit clean()
    * L-02 decimal validators inherit from model definitions
    * L-14 per-workflow forms (resolve / false_positive / etc.) require notes
    * AlertRuleForm enforces XOR scope: exactly one of
      (device_tag, scope_device, scope_asset) is set
"""
from decimal import Decimal

from django import forms
from django.utils import timezone

from . import models


# ============================================================================
# Mixin: tenant-aware ModelForm with stash
# ============================================================================

class TenantAwareModelForm(forms.ModelForm):
    """Stashes tenant on __init__ so clean() can scope unique_together checks (L-01)."""

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        self._scope_querysets()

    def _scope_querysets(self):
        """Subclasses override to scope FK choices to ``self._tenant``."""
        return None


# ============================================================================
# 15.1  Connectivity Hub
# ============================================================================

class DeviceProtocolForm(forms.ModelForm):
    class Meta:
        model = models.DeviceProtocol
        fields = ('code', 'name', 'default_port', 'description', 'is_active')

    def clean_code(self):
        code = self.cleaned_data.get('code', '').strip()
        if not code:
            raise forms.ValidationError('Code is required.')
        qs = models.DeviceProtocol.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('A protocol with this code already exists.')
        return code


class DeviceBrokerForm(TenantAwareModelForm):
    class Meta:
        model = models.DeviceBroker
        fields = (
            'name', 'protocol', 'host', 'port', 'auth_method',
            'username', 'tls_enabled', 'ca_cert_filename',
        )

    def _scope_querysets(self):
        self.fields['protocol'].queryset = models.DeviceProtocol.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        # L-01 unique_together (tenant, name)
        name = cleaned.get('name')
        if name and self._tenant is not None:
            qs = models.DeviceBroker.objects.filter(tenant=self._tenant, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError({'name': 'A broker with this name already exists.'})
        return cleaned


class DeviceForm(TenantAwareModelForm):
    class Meta:
        model = models.Device
        fields = (
            'name', 'broker', 'protocol', 'asset', 'device_type',
            'serial_number', 'firmware_version', 'location_text', 'notes',
        )

    def _scope_querysets(self):
        if self._tenant is not None:
            self.fields['broker'].queryset = models.DeviceBroker.objects.filter(tenant=self._tenant)
        self.fields['protocol'].queryset = models.DeviceProtocol.objects.filter(is_active=True)
        if self._tenant is not None:
            from apps.eam.models import Asset
            self.fields['asset'].queryset = Asset.objects.filter(tenant=self._tenant)
            self.fields['asset'].required = False

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get('name')
        if name and self._tenant is not None:
            qs = models.Device.objects.filter(tenant=self._tenant, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError({'name': 'A device with this name already exists.'})
        return cleaned


class DeviceTagForm(TenantAwareModelForm):
    class Meta:
        model = models.DeviceTag
        fields = (
            'name', 'device', 'address', 'data_type', 'unit',
            'scale_factor', 'offset', 'sampling_interval_seconds',
            'condition_point', 'is_active',
        )

    def _scope_querysets(self):
        if self._tenant is not None:
            self.fields['device'].queryset = models.Device.objects.filter(tenant=self._tenant)
            from apps.eam.models import ConditionMonitoringPoint
            self.fields['condition_point'].queryset = ConditionMonitoringPoint.objects.filter(tenant=self._tenant)
            self.fields['condition_point'].required = False

    def clean(self):
        cleaned = super().clean()
        device = cleaned.get('device')
        address = cleaned.get('address')
        name = cleaned.get('name')
        if device is None or self._tenant is None:
            return cleaned
        # L-01 unique_together (tenant, device, address)
        if address:
            qs = models.DeviceTag.objects.filter(
                tenant=self._tenant, device=device, address__iexact=address,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError({'address': 'A tag with this address already exists on the device.'})
        if name:
            qs2 = models.DeviceTag.objects.filter(
                tenant=self._tenant, device=device, name__iexact=name,
            )
            if self.instance.pk:
                qs2 = qs2.exclude(pk=self.instance.pk)
            if qs2.exists():
                raise forms.ValidationError({'name': 'A tag with this name already exists on the device.'})
        return cleaned


# ============================================================================
# 15.2  Real-Time Data Acquisition
# ============================================================================

class IoTReadingForm(TenantAwareModelForm):
    class Meta:
        model = models.IoTReading
        fields = (
            'device_tag', 'timestamp', 'value_numeric', 'value_text',
            'value_bool', 'quality', 'source', 'notes',
        )

    def _scope_querysets(self):
        if self._tenant is not None:
            self.fields['device_tag'].queryset = models.DeviceTag.objects.filter(
                tenant=self._tenant, is_active=True,
            )

    def clean(self):
        cleaned = super().clean()
        v_num = cleaned.get('value_numeric')
        v_text = cleaned.get('value_text')
        v_bool = cleaned.get('value_bool')
        if v_num is None and not v_text and v_bool is None:
            raise forms.ValidationError('Provide one of value_numeric / value_text / value_bool.')
        return cleaned


class IoTReadingIngestForm(forms.Form):
    """JSON / CSV bulk ingest payload."""

    payload = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 12, 'class': 'font-monospace'}),
        help_text='JSON array of {tag_address, timestamp, value} OR CSV with same columns.',
    )
    source_format = forms.ChoiceField(
        choices=[('json', 'JSON'), ('csv', 'CSV')], initial='json',
    )
    notes = forms.CharField(required=False, max_length=255)


class EdgeProcessorForm(TenantAwareModelForm):
    class Meta:
        model = models.EdgeProcessor
        fields = (
            'name', 'input_tag', 'transform_type', 'window_seconds',
            'threshold_value', 'output_tag', 'is_active', 'description',
        )

    def _scope_querysets(self):
        if self._tenant is not None:
            qs = models.DeviceTag.objects.filter(tenant=self._tenant)
            self.fields['input_tag'].queryset = qs
            self.fields['output_tag'].queryset = qs
            self.fields['output_tag'].required = False

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get('name')
        if name and self._tenant is not None:
            qs = models.EdgeProcessor.objects.filter(tenant=self._tenant, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError({'name': 'An edge processor with this name already exists.'})
        return cleaned


# ============================================================================
# 15.3  Digital Twin Configuration
# ============================================================================

class DigitalTwinForm(TenantAwareModelForm):
    class Meta:
        model = models.DigitalTwin
        fields = (
            'name', 'asset', 'twin_type', 'description',
            'model_version', 'config',
        )

    def _scope_querysets(self):
        if self._tenant is not None:
            from apps.eam.models import Asset
            self.fields['asset'].queryset = Asset.objects.filter(tenant=self._tenant)
            self.fields['asset'].required = False

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get('name')
        version = cleaned.get('model_version') or '1.0.0'
        if name and self._tenant is not None:
            qs = models.DigitalTwin.objects.filter(
                tenant=self._tenant, name__iexact=name, model_version=version,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    'A digital twin with this name and model version already exists.'
                )
        return cleaned


class TwinStateAttributeForm(TenantAwareModelForm):
    class Meta:
        model = models.TwinStateAttribute
        fields = (
            'twin', 'name', 'attribute_type', 'source_tag',
            'formula', 'unit',
        )

    def _scope_querysets(self):
        if self._tenant is not None:
            self.fields['twin'].queryset = models.DigitalTwin.objects.filter(tenant=self._tenant)
            self.fields['source_tag'].queryset = models.DeviceTag.objects.filter(tenant=self._tenant)
            self.fields['source_tag'].required = False

    def clean(self):
        cleaned = super().clean()
        attr_type = cleaned.get('attribute_type')
        formula = (cleaned.get('formula') or '').strip()
        source_tag = cleaned.get('source_tag')
        if attr_type == 'derived' and not formula:
            raise forms.ValidationError({'formula': 'Derived attributes require a formula.'})
        if attr_type in ('state', 'measurement') and source_tag is None:
            raise forms.ValidationError({'source_tag': 'Source tag is required for state/measurement attributes.'})
        # L-01 unique_together (tenant, twin, name)
        twin = cleaned.get('twin')
        name = cleaned.get('name')
        if twin and name and self._tenant is not None:
            qs = models.TwinStateAttribute.objects.filter(
                tenant=self._tenant, twin=twin, name__iexact=name,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError({'name': 'An attribute with this name already exists on the twin.'})
        return cleaned


class TwinSimulationScenarioForm(TenantAwareModelForm):
    class Meta:
        model = models.TwinSimulationScenario
        fields = ('twin', 'name', 'description', 'input_payload', 'expected_output')

    def _scope_querysets(self):
        if self._tenant is not None:
            self.fields['twin'].queryset = models.DigitalTwin.objects.filter(tenant=self._tenant)


# ============================================================================
# 15.4  OEE Monitoring
# ============================================================================

class LossReasonForm(TenantAwareModelForm):
    class Meta:
        model = models.LossReason
        fields = ('code', 'name', 'category', 'is_planned', 'is_active', 'description')

    def clean_code(self):
        code = self.cleaned_data.get('code', '').strip()
        if code and self._tenant is not None:
            qs = models.LossReason.objects.filter(tenant=self._tenant, code__iexact=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('A loss reason with this code already exists.')
        return code


class MachineStateLogForm(TenantAwareModelForm):
    class Meta:
        model = models.MachineStateLog
        fields = ('asset', 'state', 'loss_reason', 'started_at', 'ended_at', 'notes')

    def _scope_querysets(self):
        if self._tenant is not None:
            from apps.eam.models import Asset
            self.fields['asset'].queryset = Asset.objects.filter(tenant=self._tenant)
            self.fields['loss_reason'].queryset = models.LossReason.objects.filter(
                tenant=self._tenant, is_active=True,
            )
            self.fields['loss_reason'].required = False

    def clean(self):
        cleaned = super().clean()
        started = cleaned.get('started_at')
        ended = cleaned.get('ended_at')
        if started and ended and ended < started:
            raise forms.ValidationError({'ended_at': 'Ended-at must be on or after started-at.'})
        return cleaned


class OEEPeriodForm(TenantAwareModelForm):
    class Meta:
        model = models.OEEPeriod
        fields = (
            'asset', 'shift', 'period_date',
            'planned_run_minutes', 'run_minutes',
            'ideal_cycle_seconds', 'total_count', 'good_count', 'scrap_count',
            'notes',
        )

    def _scope_querysets(self):
        if self._tenant is not None:
            from apps.eam.models import Asset
            from apps.labor.models import Shift
            self.fields['asset'].queryset = Asset.objects.filter(tenant=self._tenant)
            self.fields['shift'].queryset = Shift.objects.filter(tenant=self._tenant)
            self.fields['shift'].required = False

    def clean(self):
        cleaned = super().clean()
        # L-01 unique_together (tenant, asset, shift, period_date)
        asset = cleaned.get('asset')
        shift = cleaned.get('shift')
        period_date = cleaned.get('period_date')
        if asset and period_date and self._tenant is not None:
            qs = models.OEEPeriod.objects.filter(
                tenant=self._tenant, asset=asset, shift=shift, period_date=period_date,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    'An OEE period already exists for this asset / shift / date.'
                )
        # Sanity: good + scrap <= total
        good = cleaned.get('good_count') or Decimal('0')
        scrap = cleaned.get('scrap_count') or Decimal('0')
        total = cleaned.get('total_count') or Decimal('0')
        if (good + scrap) > total:
            raise forms.ValidationError(
                'Good count + Scrap count cannot exceed Total count.'
            )
        return cleaned


# ============================================================================
# 15.5  Alert & Anomaly Detection
# ============================================================================

class AlertRuleForm(TenantAwareModelForm):
    """XOR validation: exactly one of (device_tag, scope_device, scope_asset) set."""

    class Meta:
        model = models.AlertRule
        fields = (
            'name', 'device_tag', 'scope_device', 'scope_asset',
            'condition_type', 'threshold_high', 'threshold_low',
            'window_seconds', 'severity', 'notification_channels',
            'cooldown_seconds', 'is_active', 'description',
        )

    def _scope_querysets(self):
        if self._tenant is not None:
            self.fields['device_tag'].queryset = models.DeviceTag.objects.filter(tenant=self._tenant)
            self.fields['scope_device'].queryset = models.Device.objects.filter(tenant=self._tenant)
            from apps.eam.models import Asset
            self.fields['scope_asset'].queryset = Asset.objects.filter(tenant=self._tenant)
            self.fields['device_tag'].required = False
            self.fields['scope_device'].required = False
            self.fields['scope_asset'].required = False

    def clean_notification_channels(self):
        raw = self.cleaned_data.get('notification_channels') or 'in_app'
        valid = {'in_app', 'email', 'mes_andon'}
        parts = [p.strip() for p in raw.split(',') if p.strip()]
        bad = [p for p in parts if p not in valid]
        if bad:
            raise forms.ValidationError(
                f'Unknown channel(s): {", ".join(bad)}. Allowed: in_app, email, mes_andon.'
            )
        if not parts:
            raise forms.ValidationError('At least one channel is required.')
        return ','.join(parts)

    def clean(self):
        cleaned = super().clean()
        scope_count = sum(
            1 for f in ('device_tag', 'scope_device', 'scope_asset')
            if cleaned.get(f) is not None
        )
        if scope_count != 1:
            raise forms.ValidationError(
                'Exactly one of Device Tag, Scope Device, or Scope Asset must be set.'
            )
        # threshold guards
        cond = cleaned.get('condition_type')
        if cond == 'threshold_high' and cleaned.get('threshold_high') is None:
            raise forms.ValidationError({'threshold_high': 'High threshold is required.'})
        if cond == 'threshold_low' and cleaned.get('threshold_low') is None:
            raise forms.ValidationError({'threshold_low': 'Low threshold is required.'})
        if cond == 'range_outside':
            if cleaned.get('threshold_high') is None or cleaned.get('threshold_low') is None:
                raise forms.ValidationError('Range condition requires both high and low thresholds.')
        # L-01 unique_together (tenant, name)
        name = cleaned.get('name')
        if name and self._tenant is not None:
            qs = models.AlertRule.objects.filter(tenant=self._tenant, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError({'name': 'A rule with this name already exists.'})
        return cleaned


# ============================================================================
# Per-workflow forms (L-14)
# ============================================================================

class AnomalyAcknowledgeForm(forms.Form):
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))


class AnomalyResolveForm(forms.Form):
    """L-14: resolution_notes are mandatory at resolve transition."""
    resolution_notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Required - describe the root cause and remediation.',
    )

    def clean_resolution_notes(self):
        v = (self.cleaned_data.get('resolution_notes') or '').strip()
        if not v:
            raise forms.ValidationError('Resolution notes are required.')
        return v


class AnomalyFalsePositiveForm(forms.Form):
    """L-14: explanation required when marking false_positive so the rule can be tuned."""
    resolution_notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Required - explain why this is a false positive.',
    )

    def clean_resolution_notes(self):
        v = (self.cleaned_data.get('resolution_notes') or '').strip()
        if not v:
            raise forms.ValidationError('A justification is required when marking as false positive.')
        return v


class TwinSnapshotForm(forms.Form):
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))


class DeviceRetireForm(forms.Form):
    reason = forms.CharField(required=False, max_length=255)


class BrokerHeartbeatForm(forms.Form):
    """Stub heartbeat endpoint - records a successful ping or an error."""
    success = forms.BooleanField(required=False, initial=True)
    error_message = forms.CharField(required=False, max_length=255)
