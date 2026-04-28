"""ModelForms for Shop Floor Control CRUD.

Per Lesson L-01, every form whose Meta.fields excludes ``tenant`` performs
its own duplicate check inside ``clean()``.

Per Lesson L-02, decimal quantity / time / minutes fields rely on the
model-level MinValueValidator / MaxValueValidator stack.
"""
import os
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model

from apps.plm.models import Product
from apps.pps.models import RoutingOperation, WorkCenter

from .models import (
    AndonAlert, MESWorkOrder, OperatorTimeLog, ProductionReport,
    ShopFloorOperator, WorkInstruction, WorkInstructionAcknowledgement,
    WorkInstructionVersion,
    WORK_INSTRUCTION_FILE_EXT_ALLOWLIST, WORK_INSTRUCTION_FILE_MAX_BYTES,
)

User = get_user_model()


# ---------------- 6.1  Work Order Execution ----------------

class MESWorkOrderForm(forms.ModelForm):
    """Mostly read-only after dispatch - but admins can adjust priority + notes."""

    class Meta:
        model = MESWorkOrder
        fields = ('priority', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 3})}


# ---------------- 6.2  Operators ----------------

class ShopFloorOperatorForm(forms.ModelForm):
    class Meta:
        model = ShopFloorOperator
        fields = ('user', 'badge_number', 'default_work_center', 'is_active', 'notes')

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if tenant is not None:
            self.fields['user'].queryset = User.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['default_work_center'].queryset = WorkCenter.objects.filter(
                tenant=tenant, is_active=True,
            )

    def clean(self):
        cleaned = super().clean()
        badge = cleaned.get('badge_number')
        user = cleaned.get('user')
        if self._tenant and badge:
            qs = ShopFloorOperator.all_objects.filter(
                tenant=self._tenant, badge_number=badge,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('badge_number', 'Badge number already issued in this tenant.')
        if self._tenant and user:
            qs = ShopFloorOperator.all_objects.filter(tenant=self._tenant, user=user)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('user', 'This user already has a shop-floor operator profile.')
        return cleaned


# ---------------- 6.3  Production Reports ----------------

class ProductionReportForm(forms.ModelForm):
    class Meta:
        model = ProductionReport
        fields = ('good_qty', 'scrap_qty', 'rework_qty', 'scrap_reason',
                  'cycle_time_minutes', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def clean(self):
        cleaned = super().clean()
        good = cleaned.get('good_qty') or Decimal('0')
        scrap = cleaned.get('scrap_qty') or Decimal('0')
        rework = cleaned.get('rework_qty') or Decimal('0')
        if good + scrap + rework <= 0:
            raise forms.ValidationError(
                'At least one of good / scrap / rework must be greater than zero.'
            )
        if scrap > 0 and not cleaned.get('scrap_reason'):
            self.add_error('scrap_reason', 'Pick a scrap reason when scrap > 0.')
        return cleaned


# ---------------- 6.4  Andon Alerts ----------------

class AndonAlertForm(forms.ModelForm):
    class Meta:
        model = AndonAlert
        fields = ('alert_type', 'severity', 'title', 'message', 'work_center',
                  'work_order', 'work_order_operation')
        widgets = {'message': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['work_center'].queryset = WorkCenter.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['work_order'].queryset = MESWorkOrder.objects.filter(
                tenant=tenant,
            ).exclude(status__in=('completed', 'cancelled'))
            self.fields['work_order'].required = False
            self.fields['work_order_operation'].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('alert_type') == 'other' and not cleaned.get('title', '').strip():
            self.add_error('title', 'Title is required when alert type is Other.')
        return cleaned


class AndonResolveForm(forms.ModelForm):
    class Meta:
        model = AndonAlert
        fields = ('resolution_notes',)
        widgets = {'resolution_notes': forms.Textarea(attrs={'rows': 3})}

    def clean_resolution_notes(self):
        # The model field is blank=True (so non-resolution edits don't require
        # it), but RESOLVING the alert requires a real note for traceability.
        notes = (self.cleaned_data.get('resolution_notes') or '').strip()
        if not notes:
            raise forms.ValidationError(
                'A resolution note is required when resolving an alert.'
            )
        return notes


# ---------------- 6.5  Work Instructions ----------------

class WorkInstructionForm(forms.ModelForm):
    class Meta:
        model = WorkInstruction
        fields = ('title', 'doc_type', 'routing_operation', 'product')

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['routing_operation'].queryset = RoutingOperation.objects.filter(
                tenant=tenant,
            ).select_related('routing__product')
            self.fields['routing_operation'].required = False
            self.fields['product'].queryset = Product.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')
            self.fields['product'].required = False

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('routing_operation') and not cleaned.get('product'):
            raise forms.ValidationError(
                'Link the instruction to a routing operation, a product, or both.'
            )
        return cleaned


class WorkInstructionVersionForm(forms.ModelForm):
    class Meta:
        model = WorkInstructionVersion
        fields = ('version', 'content', 'attachment', 'video_url', 'change_notes')
        widgets = {
            'content': forms.Textarea(attrs={'rows': 8}),
            'change_notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, tenant=None, instruction=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        self._instruction = instruction

    def clean_attachment(self):
        attachment = self.cleaned_data.get('attachment')
        if not attachment:
            return attachment
        ext = os.path.splitext(attachment.name)[1].lower()
        if ext not in WORK_INSTRUCTION_FILE_EXT_ALLOWLIST:
            raise forms.ValidationError(
                f'Unsupported file type. Allowed: {", ".join(WORK_INSTRUCTION_FILE_EXT_ALLOWLIST)}.'
            )
        if attachment.size and attachment.size > WORK_INSTRUCTION_FILE_MAX_BYTES:
            raise forms.ValidationError('File exceeds the 25 MB limit.')
        return attachment

    def clean(self):
        cleaned = super().clean()
        version = (cleaned.get('version') or '').strip()
        if version and self._instruction is not None:
            qs = WorkInstructionVersion.all_objects.filter(
                instruction=self._instruction, version=version,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('version', 'A version with this label already exists for this instruction.')
        return cleaned


class WorkInstructionAcknowledgementForm(forms.ModelForm):
    class Meta:
        model = WorkInstructionAcknowledgement
        fields = ('signature_text',)

    def clean_signature_text(self):
        sig = (self.cleaned_data.get('signature_text') or '').strip()
        if not sig:
            raise forms.ValidationError('Type your name to confirm acknowledgement.')
        return sig


# ---------------- Time-log filter form (read-only list) ----------------

class TimeLogFilterForm(forms.Form):
    """Light-weight GET form used by the time-log list page filters."""

    operator = forms.ModelChoiceField(
        queryset=ShopFloorOperator.objects.none(), required=False,
    )
    action = forms.ChoiceField(
        choices=[('', 'Any action')] + list(OperatorTimeLog.ACTION_CHOICES),
        required=False,
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['operator'].queryset = ShopFloorOperator.objects.filter(
                tenant=tenant,
            ).select_related('user')
