"""Module 20 - Workflow & Business Process Automation forms.

Every tenant-scoped ModelForm accepts ``tenant=`` in __init__ and uses
that tenant to (a) scope every FK queryset and (b) drive an explicit
``clean()`` for any unique_together that excludes ``tenant`` (L-01).

Per-workflow forms (reject / delegate / cancel / dismiss) live at the
bottom of the file and require notes / target user where applicable
(L-14).
"""
from __future__ import annotations

import json

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from . import models as M


User = get_user_model()


# ----------------------------------------------------------------------------
# 20.1  Visual Workflow Designer
# ----------------------------------------------------------------------------

class _TenantMixin(forms.ModelForm):
    """Stash tenant + caller user, prune system fields, scope FK querysets."""

    def __init__(self, *args, tenant=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        self._user = user


class ProcessCategoryForm(_TenantMixin):
    class Meta:
        model = M.ProcessCategory
        fields = ['name', 'code', 'description', 'is_active']

    def clean(self):
        cleaned = super().clean()
        code = (cleaned.get('code') or '').strip()
        if self._tenant and code:
            qs = M.ProcessCategory.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError({'code': 'A category with this code already exists.'})
        return cleaned


class ProcessDefinitionForm(_TenantMixin):
    class Meta:
        model = M.ProcessDefinition
        fields = ['name', 'version', 'category', 'description', 'status', 'owner', 'is_default']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['category'].queryset = M.ProcessCategory.all_objects.filter(tenant=self._tenant)
            self.fields['owner'].queryset = User.objects.filter(tenant=self._tenant) if hasattr(User, 'tenant') else User.objects.all()


class ProcessNodeForm(_TenantMixin):
    class Meta:
        model = M.ProcessNode
        fields = ['definition', 'node_key', 'node_type', 'name', 'lane', 'position_x', 'position_y', 'order']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['definition'].queryset = M.ProcessDefinition.all_objects.filter(tenant=self._tenant)

    def clean(self):
        cleaned = super().clean()
        definition = cleaned.get('definition')
        node_key = (cleaned.get('node_key') or '').strip()
        if definition and node_key:
            qs = M.ProcessNode.all_objects.filter(definition=definition, node_key=node_key)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError({'node_key': 'A node with this key already exists in the definition.'})
        return cleaned


class ProcessTransitionForm(_TenantMixin):
    class Meta:
        model = M.ProcessTransition
        fields = ['definition', 'from_node', 'to_node', 'name', 'condition_expr']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['definition'].queryset = M.ProcessDefinition.all_objects.filter(tenant=self._tenant)
            self.fields['from_node'].queryset = M.ProcessNode.all_objects.filter(tenant=self._tenant)
            self.fields['to_node'].queryset = M.ProcessNode.all_objects.filter(tenant=self._tenant)


class ProcessInstanceForm(_TenantMixin):
    class Meta:
        model = M.ProcessInstance
        fields = ['definition', 'business_object_type', 'business_object_id', 'notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['definition'].queryset = M.ProcessDefinition.all_objects.filter(tenant=self._tenant, status='active')


# ----------------------------------------------------------------------------
# 20.2  Approval Engine
# ----------------------------------------------------------------------------

class ApprovalPolicyForm(_TenantMixin):
    class Meta:
        model = M.ApprovalPolicy
        fields = ['name', 'code', 'description', 'applies_to_type', 'is_active']

    def clean(self):
        cleaned = super().clean()
        code = (cleaned.get('code') or '').strip()
        if self._tenant and code:
            qs = M.ApprovalPolicy.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError({'code': 'A policy with this code already exists.'})
        return cleaned


class ApprovalLevelForm(_TenantMixin):
    class Meta:
        model = M.ApprovalLevel
        fields = ['policy', 'level_no', 'name', 'approver_role', 'min_approvers', 'sla_hours', 'allow_delegation']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['policy'].queryset = M.ApprovalPolicy.all_objects.filter(tenant=self._tenant)


class EscalationRuleForm(_TenantMixin):
    class Meta:
        model = M.EscalationRule
        fields = ['policy', 'level_no', 'trigger_hours_overdue', 'escalate_to_role', 'notify_channels']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['policy'].queryset = M.ApprovalPolicy.all_objects.filter(tenant=self._tenant)


class ApprovalRequestForm(_TenantMixin):
    class Meta:
        model = M.ApprovalRequest
        fields = ['policy', 'subject', 'business_object_type', 'business_object_id', 'notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['policy'].queryset = M.ApprovalPolicy.all_objects.filter(tenant=self._tenant, is_active=True)


class ApprovalDelegationForm(_TenantMixin):
    class Meta:
        model = M.ApprovalDelegation
        fields = ['delegator', 'delegate', 'policy', 'starts_at', 'ends_at', 'reason', 'is_active']
        widgets = {
            'starts_at': forms.DateInput(attrs={'type': 'date'}),
            'ends_at': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['policy'].queryset = M.ApprovalPolicy.all_objects.filter(tenant=self._tenant)
            qs = User.objects.filter(tenant=self._tenant) if hasattr(User, 'tenant') else User.objects.all()
            self.fields['delegator'].queryset = qs
            self.fields['delegate'].queryset = qs

    def clean(self):
        cleaned = super().clean()
        delegator = cleaned.get('delegator')
        delegate = cleaned.get('delegate')
        starts = cleaned.get('starts_at')
        ends = cleaned.get('ends_at')
        if delegator and delegate and delegator == delegate:
            raise forms.ValidationError('Delegator and delegate must be different users.')
        if starts and ends and ends < starts:
            raise forms.ValidationError({'ends_at': 'End date must be on or after start date.'})
        return cleaned


# ----------------------------------------------------------------------------
# 20.3  Notification & Escalation Matrix
# ----------------------------------------------------------------------------

class NotificationChannelForm(_TenantMixin):
    class Meta:
        model = M.NotificationChannel
        fields = ['code', 'name', 'is_active', 'config_json']

    def clean(self):
        cleaned = super().clean()
        code = cleaned.get('code')
        if self._tenant and code:
            qs = M.NotificationChannel.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError({'code': 'A channel with this code already exists.'})
        return cleaned


class NotificationTemplateForm(_TenantMixin):
    channels_csv = forms.CharField(
        required=False,
        help_text='Comma-separated channel codes, e.g. email,in_app',
    )

    class Meta:
        model = M.NotificationTemplate
        fields = ['code', 'name', 'event_type', 'subject_template', 'body_template', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        existing = self.instance.channels if self.instance and self.instance.pk else []
        if isinstance(existing, list):
            self.fields['channels_csv'].initial = ','.join(existing)

    def clean(self):
        cleaned = super().clean()
        code = (cleaned.get('code') or '').strip()
        if self._tenant and code:
            qs = M.NotificationTemplate.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError({'code': 'A template with this code already exists.'})
        return cleaned

    def save(self, commit=True):
        raw = (self.cleaned_data.get('channels_csv') or '').strip()
        codes = [c.strip() for c in raw.split(',') if c.strip()] if raw else []
        self.instance.channels = codes
        return super().save(commit=commit)


class NotificationRuleForm(_TenantMixin):
    class Meta:
        model = M.NotificationRule
        fields = ['name', 'event_type', 'template', 'delay_minutes', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['template'].queryset = M.NotificationTemplate.all_objects.filter(tenant=self._tenant, is_active=True)


# ----------------------------------------------------------------------------
# 20.4  Integration Orchestration
# ----------------------------------------------------------------------------

class ConnectorForm(_TenantMixin):
    class Meta:
        model = M.Connector
        fields = ['name', 'connector_type', 'base_url', 'auth_method', 'auth_secret_hash', 'is_active', 'description']
        widgets = {
            'auth_secret_hash': forms.PasswordInput(render_value=True),
        }


class ConnectorEndpointForm(_TenantMixin):
    class Meta:
        model = M.ConnectorEndpoint
        fields = ['connector', 'name', 'path', 'method', 'headers_json', 'request_template', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['connector'].queryset = M.Connector.all_objects.filter(tenant=self._tenant)

    def clean(self):
        cleaned = super().clean()
        connector = cleaned.get('connector')
        name = (cleaned.get('name') or '').strip()
        if connector and name:
            qs = M.ConnectorEndpoint.all_objects.filter(connector=connector, name=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError({'name': 'An endpoint with this name already exists.'})
        return cleaned


class IntegrationFlowForm(_TenantMixin):
    class Meta:
        model = M.IntegrationFlow
        fields = ['code', 'name', 'description', 'trigger_type', 'trigger_config', 'is_active']

    def clean(self):
        cleaned = super().clean()
        code = (cleaned.get('code') or '').strip()
        if self._tenant and code:
            qs = M.IntegrationFlow.all_objects.filter(tenant=self._tenant, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError({'code': 'A flow with this code already exists.'})
        return cleaned


class FlowStepForm(_TenantMixin):
    class Meta:
        model = M.FlowStep
        fields = ['flow', 'step_no', 'name', 'step_type', 'endpoint', 'config_json', 'on_failure']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['flow'].queryset = M.IntegrationFlow.all_objects.filter(tenant=self._tenant)
            self.fields['endpoint'].queryset = M.ConnectorEndpoint.all_objects.filter(tenant=self._tenant, is_active=True)


# ----------------------------------------------------------------------------
# 20.5  Process Mining & Optimization
# ----------------------------------------------------------------------------

class BottleneckAnalysisForm(_TenantMixin):
    class Meta:
        model = M.BottleneckAnalysis
        fields = ['definition', 'period_start', 'period_end', 'notes']
        widgets = {
            'period_start': forms.DateInput(attrs={'type': 'date'}),
            'period_end': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['definition'].queryset = M.ProcessDefinition.all_objects.filter(tenant=self._tenant)

    def clean(self):
        cleaned = super().clean()
        s = cleaned.get('period_start')
        e = cleaned.get('period_end')
        if s and e and e < s:
            raise forms.ValidationError({'period_end': 'End date must be on or after start date.'})
        return cleaned


class ProcessOptimizationSuggestionForm(_TenantMixin):
    class Meta:
        model = M.ProcessOptimizationSuggestion
        fields = ['definition', 'analysis', 'suggestion_type', 'description', 'expected_savings_pct', 'notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._tenant:
            self.fields['definition'].queryset = M.ProcessDefinition.all_objects.filter(tenant=self._tenant)
            self.fields['analysis'].queryset = M.BottleneckAnalysis.all_objects.filter(tenant=self._tenant)


# ----------------------------------------------------------------------------
# Workflow-only forms (L-14: per-transition required fields)
# ----------------------------------------------------------------------------

class ApprovalDecisionForm(forms.Form):
    """Used by approve / reject endpoints."""

    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)


class ApprovalRejectForm(forms.Form):
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=True,
        help_text='Reason is required when rejecting.',
    )


class ApprovalDelegateActionForm(forms.Form):
    delegate_id = forms.IntegerField(min_value=1, required=True)
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)


class ProcessInstanceCancelForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=True,
        help_text='Reason is required when cancelling.',
    )


class SuggestionStatusForm(forms.Form):
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=True,
        help_text='Notes required for dismiss / apply.',
    )
