"""Django admin registration for Module 18 - Returns & RMA Management."""
from django.contrib import admin

from .models import (
    FailureMode,
    RMAApproval,
    RMALine,
    RMARequest,
    RMAReason,
    RepairLaborLog,
    RepairOrder,
    RepairPartUsage,
    ReturnAnalysis,
    ReturnReceipt,
    ReturnReceiptLine,
    RootCauseCategory,
    SupplierChargeback,
    WarrantyClaim,
    WarrantyPolicy,
    WarrantyRegistration,
)


# ----- 18.1  RMA Request & Authorization -----

@admin.register(RMAReason)
class RMAReasonAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_active', 'tenant')
    list_filter = ('category', 'is_active', 'tenant')
    search_fields = ('name', 'description')


class RMALineInline(admin.TabularInline):
    model = RMALine
    extra = 0
    autocomplete_fields = ('product', 'reason')


class RMAApprovalInline(admin.TabularInline):
    model = RMAApproval
    extra = 0
    readonly_fields = ('action', 'from_status', 'to_status', 'performed_by', 'performed_at')


@admin.register(RMARequest)
class RMARequestAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'customer', 'status', 'requested_action',
        'request_date', 'tenant',
    )
    list_filter = ('status', 'requested_action', 'tenant')
    search_fields = ('code', 'customer__name', 'customer_reference', 'reason_summary')
    date_hierarchy = 'request_date'
    inlines = [RMALineInline, RMAApprovalInline]
    readonly_fields = ('code', 'submitted_at', 'decided_at')


@admin.register(RMALine)
class RMALineAdmin(admin.ModelAdmin):
    list_display = (
        'rma', 'line_no', 'product', 'quantity', 'reason',
        'condition_reported', 'tenant',
    )
    list_filter = ('condition_reported', 'tenant')
    search_fields = ('rma__code', 'product__name', 'serial_number', 'lot_number')


@admin.register(RMAApproval)
class RMAApprovalAdmin(admin.ModelAdmin):
    list_display = ('rma', 'action', 'from_status', 'to_status', 'performed_by', 'performed_at')
    list_filter = ('action', 'tenant')
    search_fields = ('rma__code', 'notes')
    readonly_fields = ('performed_at',)


# ----- 18.2  Returns Receiving & Inspection -----

class ReturnReceiptLineInline(admin.TabularInline):
    model = ReturnReceiptLine
    extra = 0
    autocomplete_fields = ('rma_line',)
    readonly_fields = ('disposition_done', 'stock_movement')


@admin.register(ReturnReceipt)
class ReturnReceiptAdmin(admin.ModelAdmin):
    list_display = ('code', 'rma', 'status', 'warehouse', 'received_date', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('code', 'rma__code', 'tracking_number')
    date_hierarchy = 'received_date'
    inlines = [ReturnReceiptLineInline]
    readonly_fields = ('code',)


@admin.register(ReturnReceiptLine)
class ReturnReceiptLineAdmin(admin.ModelAdmin):
    list_display = (
        'receipt', 'rma_line', 'quantity_received', 'condition_assessed',
        'disposition', 'disposition_done', 'tenant',
    )
    list_filter = ('condition_assessed', 'disposition', 'disposition_done', 'tenant')
    search_fields = ('receipt__code', 'rma_line__rma__code')


# ----- 18.3  Repair & Refurbishment Tracking -----

class RepairPartUsageInline(admin.TabularInline):
    model = RepairPartUsage
    extra = 0
    autocomplete_fields = ('part',)
    readonly_fields = ('line_cost', 'stock_movement')


class RepairLaborLogInline(admin.TabularInline):
    model = RepairLaborLog
    extra = 0
    autocomplete_fields = ('employee',)
    readonly_fields = ('labor_cost', 'labor_booking')


@admin.register(RepairOrder)
class RepairOrderAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'product', 'order_type', 'status',
        'actual_cost', 'labor_minutes', 'tenant',
    )
    list_filter = ('status', 'order_type', 'tenant')
    search_fields = ('code', 'product__name', 'problem_description')
    inlines = [RepairPartUsageInline, RepairLaborLogInline]
    readonly_fields = ('code', 'actual_cost', 'labor_minutes', 'started_at', 'completed_at')


@admin.register(RepairPartUsage)
class RepairPartUsageAdmin(admin.ModelAdmin):
    list_display = ('repair_order', 'part', 'quantity', 'unit_cost', 'line_cost', 'tenant')
    list_filter = ('tenant',)
    search_fields = ('repair_order__code', 'part__name')


@admin.register(RepairLaborLog)
class RepairLaborLogAdmin(admin.ModelAdmin):
    list_display = (
        'repair_order', 'employee', 'work_date', 'minutes',
        'hourly_rate', 'labor_cost', 'tenant',
    )
    list_filter = ('tenant',)
    search_fields = ('repair_order__code',)
    readonly_fields = ('labor_cost', 'labor_booking')


# ----- 18.4  Warranty Management -----

@admin.register(WarrantyPolicy)
class WarrantyPolicyAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'name', 'coverage_type', 'duration_months', 'is_active', 'tenant',
    )
    list_filter = ('coverage_type', 'is_active', 'tenant')
    search_fields = ('code', 'name')
    autocomplete_fields = ('product', 'product_category')
    readonly_fields = ('code',)


class WarrantyClaimInline(admin.TabularInline):
    model = WarrantyClaim
    extra = 0
    readonly_fields = ('code', 'decided_at', 'replacement_order')


@admin.register(WarrantyRegistration)
class WarrantyRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'product', 'customer', 'policy', 'serial_number',
        'start_date', 'end_date', 'status', 'tenant',
    )
    list_filter = ('status', 'tenant')
    search_fields = ('code', 'serial_number', 'customer__name', 'product__name')
    date_hierarchy = 'start_date'
    inlines = [WarrantyClaimInline]
    readonly_fields = ('code', 'end_date')


@admin.register(WarrantyClaim)
class WarrantyClaimAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'registration', 'status', 'resolution',
        'claim_date', 'replacement_order', 'tenant',
    )
    list_filter = ('status', 'resolution', 'tenant')
    search_fields = ('code', 'registration__code', 'defect_description')
    date_hierarchy = 'claim_date'
    readonly_fields = ('code', 'decided_at', 'replacement_order')


# ----- 18.5  Returns Analytics -----

@admin.register(FailureMode)
class FailureModeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_active', 'tenant')
    list_filter = ('category', 'is_active', 'tenant')
    search_fields = ('name', 'description')


@admin.register(RootCauseCategory)
class RootCauseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'responsible_area', 'is_active', 'tenant')
    list_filter = ('responsible_area', 'is_active', 'tenant')
    search_fields = ('name', 'description')


class SupplierChargebackInline(admin.TabularInline):
    model = SupplierChargeback
    extra = 0
    readonly_fields = ('code', 'issued_date', 'recovered_date')


@admin.register(ReturnAnalysis)
class ReturnAnalysisAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'rma_line', 'failure_mode', 'root_cause_category',
        'supplier', 'analyzed_at', 'tenant',
    )
    list_filter = ('failure_mode', 'root_cause_category', 'tenant')
    search_fields = ('code', 'rma_line__rma__code', 'analysis_notes')
    inlines = [SupplierChargebackInline]
    readonly_fields = ('code',)


@admin.register(SupplierChargeback)
class SupplierChargebackAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'analysis', 'supplier', 'amount', 'currency',
        'status', 'issued_date', 'tenant',
    )
    list_filter = ('status', 'currency', 'tenant')
    search_fields = ('code', 'supplier__name', 'reference')
    readonly_fields = ('code',)
