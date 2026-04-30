"""ModelForms for Quality Management CRUD.

Per Lesson L-01, every form whose Meta.fields excludes ``tenant`` performs
its own duplicate check inside ``clean()``.

Per Lesson L-02, decimal quantity / measurement fields rely on the
model-level MinValueValidator / MaxValueValidator stack.

Per Lesson L-14, fields that are blank-allowed at the model layer but
required at a specific workflow transition (NCR close, calibration fail
notes, etc.) get per-workflow ``clean_<field>`` overrides.
"""
import os
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model

from apps.mes.models import MESWorkOrder, MESWorkOrderOperation
from apps.plm.models import Product
from apps.pps.models import RoutingOperation, WorkCenter

from .models import (
    CALIBRATION_CERT_EXT_ALLOWLIST, IPQC_ATTACHMENT_EXT_ALLOWLIST,
    NCR_ATTACHMENT_EXT_ALLOWLIST, QMS_FILE_MAX_BYTES,
    CalibrationRecord, CalibrationStandard, CertificateOfAnalysis,
    CorrectiveAction, FinalInspection, FinalInspectionPlan, FinalTestResult,
    FinalTestSpec, IncomingInspection, IncomingInspectionPlan,
    InspectionCharacteristic, InspectionMeasurement, MeasurementEquipment,
    NCRAttachment, NonConformanceReport, PreventiveAction, ProcessInspection,
    ProcessInspectionPlan, RootCauseAnalysis, ToleranceVerification,
)

User = get_user_model()


def _validate_file(uploaded, allowlist):
    if not uploaded:
        return uploaded
    ext = os.path.splitext(uploaded.name)[1].lower()
    if ext not in allowlist:
        raise forms.ValidationError(
            f'Unsupported file type. Allowed: {", ".join(allowlist)}.'
        )
    if uploaded.size and uploaded.size > QMS_FILE_MAX_BYTES:
        raise forms.ValidationError('File exceeds the 25 MB limit.')
    return uploaded


# ============================================================================
# 7.1  IQC FORMS
# ============================================================================

class IncomingInspectionPlanForm(forms.ModelForm):
    class Meta:
        model = IncomingInspectionPlan
        fields = ('product', 'aql_level', 'sample_method', 'aql_value',
                  'version', 'description', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

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
        version = (cleaned.get('version') or '').strip()
        if self._tenant and product and version:
            qs = IncomingInspectionPlan.all_objects.filter(
                tenant=self._tenant, product=product, version=version,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'version',
                    'A plan with this product + version already exists.',
                )
        return cleaned


class InspectionCharacteristicForm(forms.ModelForm):
    class Meta:
        model = InspectionCharacteristic
        fields = ('sequence', 'name', 'characteristic_type', 'nominal',
                  'usl', 'lsl', 'unit_of_measure', 'is_critical', 'notes')


class IncomingInspectionForm(forms.ModelForm):
    class Meta:
        model = IncomingInspection
        fields = ('product', 'plan', 'supplier_name', 'po_reference',
                  'lot_number', 'received_qty', 'deviation_notes')
        widgets = {'deviation_notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')
            self.fields['plan'].queryset = IncomingInspectionPlan.objects.filter(
                tenant=tenant, is_active=True,
            ).select_related('product')
            self.fields['plan'].required = False


class InspectionMeasurementForm(forms.ModelForm):
    class Meta:
        model = InspectionMeasurement
        fields = ('characteristic', 'measured_value', 'is_pass', 'notes')


# ============================================================================
# 7.2  IPQC FORMS
# ============================================================================

class ProcessInspectionPlanForm(forms.ModelForm):
    class Meta:
        model = ProcessInspectionPlan
        fields = ('product', 'routing_operation', 'name', 'frequency',
                  'frequency_value', 'chart_type', 'subgroup_size',
                  'nominal', 'usl', 'lsl', 'unit_of_measure',
                  'is_active', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(
                tenant=tenant,
            ).exclude(status='obsolete')
            self.fields['routing_operation'].queryset = (
                RoutingOperation.objects.filter(tenant=tenant)
                .select_related('routing__product')
            )

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get('product')
        rop = cleaned.get('routing_operation')
        if self._tenant and product and rop:
            qs = ProcessInspectionPlan.all_objects.filter(
                tenant=self._tenant, product=product, routing_operation=rop,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'routing_operation',
                    'An IPQC plan already exists for this product + operation.',
                )
        return cleaned


class ProcessInspectionForm(forms.ModelForm):
    class Meta:
        model = ProcessInspection
        fields = ('plan', 'work_order_operation', 'inspected_at',
                  'subgroup_index', 'measured_value', 'result',
                  'attachment', 'notes')
        widgets = {
            'inspected_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['plan'].queryset = ProcessInspectionPlan.objects.filter(
                tenant=tenant, is_active=True,
            ).select_related('product', 'routing_operation')
            self.fields['work_order_operation'].queryset = (
                MESWorkOrderOperation.objects.filter(tenant=tenant)
                .select_related('work_order__product')
            )
            self.fields['work_order_operation'].required = False

    def clean_attachment(self):
        return _validate_file(
            self.cleaned_data.get('attachment'),
            IPQC_ATTACHMENT_EXT_ALLOWLIST,
        )


# ============================================================================
# 7.3  FQC FORMS
# ============================================================================

class FinalInspectionPlanForm(forms.ModelForm):
    class Meta:
        model = FinalInspectionPlan
        fields = ('product', 'name', 'version', 'description', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

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
        version = (cleaned.get('version') or '').strip()
        if self._tenant and product and version:
            qs = FinalInspectionPlan.all_objects.filter(
                tenant=self._tenant, product=product, version=version,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'version',
                    'A plan with this product + version already exists.',
                )
        return cleaned


class FinalTestSpecForm(forms.ModelForm):
    class Meta:
        model = FinalTestSpec
        fields = ('sequence', 'test_name', 'test_method', 'expected_result',
                  'nominal', 'usl', 'lsl', 'unit_of_measure',
                  'is_critical', 'notes')


class FinalInspectionForm(forms.ModelForm):
    class Meta:
        model = FinalInspection
        fields = ('plan', 'work_order', 'lot_number', 'quantity_tested',
                  'deviation_notes')
        widgets = {'deviation_notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['plan'].queryset = FinalInspectionPlan.objects.filter(
                tenant=tenant, is_active=True,
            ).select_related('product')
            self.fields['work_order'].queryset = MESWorkOrder.objects.filter(
                tenant=tenant,
            ).select_related('product')
            self.fields['work_order'].required = False


class FinalTestResultForm(forms.ModelForm):
    class Meta:
        model = FinalTestResult
        fields = ('spec', 'measured_value', 'measured_text', 'is_pass', 'notes')


class CertificateOfAnalysisForm(forms.ModelForm):
    class Meta:
        model = CertificateOfAnalysis
        fields = ('customer_name', 'customer_reference', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 3})}


# ============================================================================
# 7.4  NCR & CAPA FORMS
# ============================================================================

class NonConformanceReportForm(forms.ModelForm):
    class Meta:
        model = NonConformanceReport
        fields = ('source', 'severity', 'title', 'description', 'product',
                  'lot_number', 'quantity_affected', 'iqc_inspection',
                  'ipqc_inspection', 'fqc_inspection', 'assigned_to')
        widgets = {'description': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['product'].queryset = Product.objects.filter(tenant=tenant)
            self.fields['product'].required = False
            self.fields['iqc_inspection'].queryset = IncomingInspection.objects.filter(
                tenant=tenant,
            )
            self.fields['iqc_inspection'].required = False
            self.fields['ipqc_inspection'].queryset = ProcessInspection.objects.filter(
                tenant=tenant,
            )
            self.fields['ipqc_inspection'].required = False
            self.fields['fqc_inspection'].queryset = FinalInspection.objects.filter(
                tenant=tenant,
            )
            self.fields['fqc_inspection'].required = False
            self.fields['assigned_to'].queryset = User.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['assigned_to'].required = False


class NCRCloseForm(forms.ModelForm):
    """Resolution summary is required at close time (Lesson L-14)."""

    class Meta:
        model = NonConformanceReport
        fields = ('resolution_summary',)
        widgets = {'resolution_summary': forms.Textarea(attrs={'rows': 4})}

    def clean_resolution_summary(self):
        text = (self.cleaned_data.get('resolution_summary') or '').strip()
        if not text:
            raise forms.ValidationError(
                'A resolution summary is required when closing an NCR.'
            )
        return text


class RootCauseAnalysisForm(forms.ModelForm):
    class Meta:
        model = RootCauseAnalysis
        fields = ('method', 'analysis_text', 'root_cause_summary')
        widgets = {
            'analysis_text': forms.Textarea(attrs={'rows': 6}),
            'root_cause_summary': forms.Textarea(attrs={'rows': 3}),
        }


class CorrectiveActionForm(forms.ModelForm):
    class Meta:
        model = CorrectiveAction
        fields = ('sequence', 'action_text', 'owner', 'due_date',
                  'effectiveness_verified', 'verification_notes')
        widgets = {
            'action_text': forms.Textarea(attrs={'rows': 3}),
            'verification_notes': forms.Textarea(attrs={'rows': 2}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['owner'].queryset = User.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['owner'].required = False


class PreventiveActionForm(forms.ModelForm):
    class Meta:
        model = PreventiveAction
        fields = ('sequence', 'action_text', 'owner', 'due_date',
                  'effectiveness_verified', 'verification_notes')
        widgets = {
            'action_text': forms.Textarea(attrs={'rows': 3}),
            'verification_notes': forms.Textarea(attrs={'rows': 2}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['owner'].queryset = User.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['owner'].required = False


class NCRAttachmentForm(forms.ModelForm):
    class Meta:
        model = NCRAttachment
        fields = ('file', 'description')

    def clean_file(self):
        return _validate_file(
            self.cleaned_data.get('file'),
            NCR_ATTACHMENT_EXT_ALLOWLIST,
        )


# ============================================================================
# 7.5  CALIBRATION FORMS
# ============================================================================

class MeasurementEquipmentForm(forms.ModelForm):
    class Meta:
        model = MeasurementEquipment
        fields = ('name', 'equipment_type', 'serial_number', 'manufacturer',
                  'model_number', 'assigned_work_center', 'range_min',
                  'range_max', 'unit_of_measure', 'tolerance',
                  'calibration_interval_days', 'status', 'is_active', 'notes')
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if tenant is not None:
            self.fields['assigned_work_center'].queryset = WorkCenter.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['assigned_work_center'].required = False

    def clean(self):
        cleaned = super().clean()
        serial = (cleaned.get('serial_number') or '').strip()
        if self._tenant and serial:
            qs = MeasurementEquipment.all_objects.filter(
                tenant=self._tenant, serial_number=serial,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'serial_number',
                    'Serial number already used in this tenant.',
                )
        return cleaned


class CalibrationStandardForm(forms.ModelForm):
    class Meta:
        model = CalibrationStandard
        fields = ('name', 'standard_number', 'traceable_to', 'description',
                  'expiry_date', 'is_active')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant

    def clean(self):
        cleaned = super().clean()
        std = (cleaned.get('standard_number') or '').strip()
        if self._tenant and std:
            qs = CalibrationStandard.all_objects.filter(
                tenant=self._tenant, standard_number=std,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'standard_number',
                    'A standard with this number already exists in this tenant.',
                )
        return cleaned


class CalibrationRecordForm(forms.ModelForm):
    class Meta:
        model = CalibrationRecord
        fields = ('calibrated_at', 'calibrated_by', 'external_lab_name',
                  'standard', 'result', 'next_due_at', 'certificate_file',
                  'notes')
        widgets = {
            'calibrated_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'next_due_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['calibrated_by'].queryset = User.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['calibrated_by'].required = False
            self.fields['standard'].queryset = CalibrationStandard.objects.filter(
                tenant=tenant, is_active=True,
            )
            self.fields['standard'].required = False

    def clean_certificate_file(self):
        return _validate_file(
            self.cleaned_data.get('certificate_file'),
            CALIBRATION_CERT_EXT_ALLOWLIST,
        )

    def clean(self):
        cleaned = super().clean()
        # Lesson L-14: notes mandatory only when result is fail.
        result = cleaned.get('result')
        notes = (cleaned.get('notes') or '').strip()
        if result == 'fail' and not notes:
            self.add_error(
                'notes',
                'Notes are required when result is Fail.',
            )
        return cleaned


class ToleranceVerificationForm(forms.ModelForm):
    class Meta:
        model = ToleranceVerification
        fields = ('sequence', 'description', 'nominal', 'as_found', 'as_left',
                  'tolerance', 'is_within_tolerance', 'unit_of_measure')
