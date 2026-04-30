from django.contrib import admin

from .models import (
    CalibrationRecord, CalibrationStandard, CertificateOfAnalysis,
    ControlChartPoint, CorrectiveAction, FinalInspection, FinalInspectionPlan,
    FinalTestResult, FinalTestSpec, IncomingInspection, IncomingInspectionPlan,
    InspectionCharacteristic, InspectionMeasurement, MeasurementEquipment,
    NCRAttachment, NonConformanceReport, PreventiveAction, ProcessInspection,
    ProcessInspectionPlan, RootCauseAnalysis, SPCChart, ToleranceVerification,
)


# ---------------- 7.1  IQC ----------------

class InspectionCharacteristicInline(admin.TabularInline):
    model = InspectionCharacteristic
    extra = 0
    fields = ('sequence', 'name', 'characteristic_type', 'nominal',
              'usl', 'lsl', 'unit_of_measure', 'is_critical')


@admin.register(IncomingInspectionPlan)
class IncomingInspectionPlanAdmin(admin.ModelAdmin):
    list_display = ('product', 'aql_level', 'aql_value', 'sample_method',
                    'version', 'is_active', 'tenant')
    list_filter = ('aql_level', 'sample_method', 'is_active', 'tenant')
    search_fields = ('product__sku', 'product__name')
    inlines = [InspectionCharacteristicInline]


class InspectionMeasurementInline(admin.TabularInline):
    model = InspectionMeasurement
    extra = 0
    fields = ('characteristic', 'measured_value', 'is_pass', 'notes')


@admin.register(IncomingInspection)
class IncomingInspectionAdmin(admin.ModelAdmin):
    list_display = ('inspection_number', 'product', 'supplier_name',
                    'lot_number', 'received_qty', 'sample_size',
                    'status', 'inspected_at', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('inspection_number', 'product__sku', 'supplier_name',
                     'lot_number', 'po_reference')
    inlines = [InspectionMeasurementInline]


# ---------------- 7.2  IPQC ----------------

@admin.register(ProcessInspectionPlan)
class ProcessInspectionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'product', 'routing_operation', 'frequency',
                    'frequency_value', 'chart_type', 'is_active', 'tenant')
    list_filter = ('chart_type', 'frequency', 'is_active', 'tenant')
    search_fields = ('name', 'product__sku')


@admin.register(ProcessInspection)
class ProcessInspectionAdmin(admin.ModelAdmin):
    list_display = ('inspection_number', 'plan', 'subgroup_index',
                    'measured_value', 'result', 'inspected_at', 'tenant')
    list_filter = ('result', 'tenant')
    search_fields = ('inspection_number', 'plan__name')


@admin.register(SPCChart)
class SPCChartAdmin(admin.ModelAdmin):
    list_display = ('plan', 'chart_type', 'subgroup_size', 'ucl', 'cl', 'lcl',
                    'sample_size_used', 'recomputed_at', 'tenant')
    list_filter = ('chart_type', 'tenant')


@admin.register(ControlChartPoint)
class ControlChartPointAdmin(admin.ModelAdmin):
    list_display = ('chart', 'subgroup_index', 'value', 'range_value',
                    'is_out_of_control', 'recorded_at', 'tenant')
    list_filter = ('is_out_of_control', 'tenant')
    search_fields = ('chart__plan__name',)


# ---------------- 7.3  FQC ----------------

class FinalTestSpecInline(admin.TabularInline):
    model = FinalTestSpec
    extra = 0
    fields = ('sequence', 'test_name', 'test_method', 'nominal', 'usl', 'lsl',
              'unit_of_measure', 'is_critical')


@admin.register(FinalInspectionPlan)
class FinalInspectionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'product', 'version', 'is_active', 'tenant')
    list_filter = ('is_active', 'tenant')
    search_fields = ('name', 'product__sku')
    inlines = [FinalTestSpecInline]


class FinalTestResultInline(admin.TabularInline):
    model = FinalTestResult
    extra = 0
    fields = ('spec', 'measured_value', 'measured_text', 'is_pass', 'notes')


@admin.register(FinalInspection)
class FinalInspectionAdmin(admin.ModelAdmin):
    list_display = ('inspection_number', 'plan', 'work_order', 'lot_number',
                    'quantity_tested', 'status', 'inspected_at', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('inspection_number', 'lot_number',
                     'plan__product__sku', 'work_order__wo_number')
    inlines = [FinalTestResultInline]


@admin.register(CertificateOfAnalysis)
class CertificateOfAnalysisAdmin(admin.ModelAdmin):
    list_display = ('coa_number', 'inspection', 'customer_name',
                    'released_to_customer', 'issued_at', 'tenant')
    list_filter = ('released_to_customer', 'tenant')
    search_fields = ('coa_number', 'customer_name', 'customer_reference')


# ---------------- 7.4  NCR & CAPA ----------------

class CorrectiveActionInline(admin.TabularInline):
    model = CorrectiveAction
    extra = 0
    fields = ('sequence', 'action_text', 'owner', 'due_date', 'status',
              'effectiveness_verified')


class PreventiveActionInline(admin.TabularInline):
    model = PreventiveAction
    extra = 0
    fields = ('sequence', 'action_text', 'owner', 'due_date', 'status',
              'effectiveness_verified')


class NCRAttachmentInline(admin.TabularInline):
    model = NCRAttachment
    extra = 0
    fields = ('file', 'description', 'uploaded_by')


@admin.register(NonConformanceReport)
class NonConformanceReportAdmin(admin.ModelAdmin):
    list_display = ('ncr_number', 'source', 'severity', 'status', 'title',
                    'product', 'reported_at', 'tenant')
    list_filter = ('source', 'severity', 'status', 'tenant')
    search_fields = ('ncr_number', 'title', 'description', 'lot_number')
    inlines = [CorrectiveActionInline, PreventiveActionInline,
               NCRAttachmentInline]


@admin.register(RootCauseAnalysis)
class RootCauseAnalysisAdmin(admin.ModelAdmin):
    list_display = ('ncr', 'method', 'analyzed_by', 'analyzed_at', 'tenant')
    list_filter = ('method', 'tenant')
    search_fields = ('ncr__ncr_number',)


@admin.register(CorrectiveAction)
class CorrectiveActionAdmin(admin.ModelAdmin):
    list_display = ('ncr', 'sequence', 'owner', 'due_date', 'status',
                    'effectiveness_verified', 'tenant')
    list_filter = ('status', 'effectiveness_verified', 'tenant')
    search_fields = ('ncr__ncr_number', 'action_text')


@admin.register(PreventiveAction)
class PreventiveActionAdmin(admin.ModelAdmin):
    list_display = ('ncr', 'sequence', 'owner', 'due_date', 'status',
                    'effectiveness_verified', 'tenant')
    list_filter = ('status', 'effectiveness_verified', 'tenant')
    search_fields = ('ncr__ncr_number', 'action_text')


# ---------------- 7.5  Calibration Management ----------------

class CalibrationRecordInline(admin.TabularInline):
    model = CalibrationRecord
    extra = 0
    fields = ('record_number', 'calibrated_at', 'result', 'next_due_at',
              'certificate_file')
    readonly_fields = ('record_number',)


@admin.register(MeasurementEquipment)
class MeasurementEquipmentAdmin(admin.ModelAdmin):
    list_display = ('equipment_number', 'name', 'equipment_type',
                    'serial_number', 'assigned_work_center',
                    'calibration_interval_days', 'next_due_at', 'status',
                    'tenant')
    list_filter = ('equipment_type', 'status', 'tenant')
    search_fields = ('equipment_number', 'name', 'serial_number',
                     'manufacturer', 'model_number')
    inlines = [CalibrationRecordInline]


@admin.register(CalibrationStandard)
class CalibrationStandardAdmin(admin.ModelAdmin):
    list_display = ('standard_number', 'name', 'traceable_to', 'expiry_date',
                    'is_active', 'tenant')
    list_filter = ('is_active', 'tenant')
    search_fields = ('standard_number', 'name')


class ToleranceVerificationInline(admin.TabularInline):
    model = ToleranceVerification
    extra = 0
    fields = ('sequence', 'description', 'nominal', 'as_found', 'as_left',
              'tolerance', 'is_within_tolerance', 'unit_of_measure')


@admin.register(CalibrationRecord)
class CalibrationRecordAdmin(admin.ModelAdmin):
    list_display = ('record_number', 'equipment', 'calibrated_at', 'result',
                    'next_due_at', 'tenant')
    list_filter = ('result', 'tenant')
    search_fields = ('record_number', 'equipment__equipment_number',
                     'equipment__serial_number')
    inlines = [ToleranceVerificationInline]


@admin.register(ToleranceVerification)
class ToleranceVerificationAdmin(admin.ModelAdmin):
    list_display = ('record', 'sequence', 'description', 'nominal',
                    'as_found', 'as_left', 'tolerance',
                    'is_within_tolerance', 'tenant')
    list_filter = ('is_within_tolerance', 'tenant')
    search_fields = ('record__record_number', 'description')
