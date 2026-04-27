from django.contrib import admin

from .models import (
    ForecastModel, ForecastResult, ForecastRun, InventorySnapshot,
    MRPCalculation, MRPException, MRPPurchaseRequisition, MRPRun, MRPRunResult,
    NetRequirement, ScheduledReceipt, SeasonalityProfile,
)


@admin.register(ForecastModel)
class ForecastModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'method', 'period_type', 'horizon_periods', 'is_active', 'tenant')
    list_filter = ('method', 'period_type', 'is_active', 'tenant')
    search_fields = ('name',)


@admin.register(SeasonalityProfile)
class SeasonalityProfileAdmin(admin.ModelAdmin):
    list_display = ('product', 'period_type', 'period_index', 'seasonal_index', 'tenant')
    list_filter = ('period_type', 'tenant')
    search_fields = ('product__sku',)


class ForecastResultInline(admin.TabularInline):
    model = ForecastResult
    extra = 0
    fields = ('product', 'period_start', 'period_end', 'forecasted_qty', 'confidence_pct')
    readonly_fields = fields


@admin.register(ForecastRun)
class ForecastRunAdmin(admin.ModelAdmin):
    list_display = ('run_number', 'forecast_model', 'run_date', 'status',
                    'started_at', 'finished_at', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('run_number',)
    inlines = [ForecastResultInline]


@admin.register(ForecastResult)
class ForecastResultAdmin(admin.ModelAdmin):
    list_display = ('run', 'product', 'period_start', 'forecasted_qty',
                    'lower_bound', 'upper_bound', 'confidence_pct')
    search_fields = ('product__sku', 'run__run_number')


@admin.register(InventorySnapshot)
class InventorySnapshotAdmin(admin.ModelAdmin):
    list_display = ('product', 'on_hand_qty', 'safety_stock', 'reorder_point',
                    'lead_time_days', 'lot_size_method', 'as_of_date', 'tenant')
    list_filter = ('lot_size_method', 'tenant')
    search_fields = ('product__sku',)


@admin.register(ScheduledReceipt)
class ScheduledReceiptAdmin(admin.ModelAdmin):
    list_display = ('product', 'receipt_type', 'quantity', 'expected_date',
                    'reference', 'tenant')
    list_filter = ('receipt_type', 'tenant')
    search_fields = ('product__sku', 'reference')


class NetRequirementInline(admin.TabularInline):
    model = NetRequirement
    extra = 0
    fields = ('product', 'period_start', 'bom_level', 'gross_requirement',
              'projected_on_hand', 'net_requirement', 'planned_order_qty',
              'planned_release_date')
    readonly_fields = fields


@admin.register(MRPCalculation)
class MRPCalculationAdmin(admin.ModelAdmin):
    list_display = ('mrp_number', 'name', 'horizon_start', 'horizon_end',
                    'time_bucket', 'status', 'tenant')
    list_filter = ('status', 'time_bucket', 'tenant')
    search_fields = ('mrp_number', 'name')
    inlines = [NetRequirementInline]


@admin.register(NetRequirement)
class NetRequirementAdmin(admin.ModelAdmin):
    list_display = ('mrp_calculation', 'product', 'period_start', 'bom_level',
                    'gross_requirement', 'net_requirement', 'planned_order_qty')
    list_filter = ('lot_size_method',)
    search_fields = ('product__sku', 'mrp_calculation__mrp_number')


@admin.register(MRPPurchaseRequisition)
class MRPPurchaseRequisitionAdmin(admin.ModelAdmin):
    list_display = ('pr_number', 'product', 'quantity', 'required_by_date',
                    'priority', 'status', 'tenant')
    list_filter = ('status', 'priority', 'tenant')
    search_fields = ('pr_number', 'product__sku')


@admin.register(MRPException)
class MRPExceptionAdmin(admin.ModelAdmin):
    list_display = ('exception_type', 'product', 'severity', 'status',
                    'recommended_action', 'created_at', 'tenant')
    list_filter = ('exception_type', 'severity', 'status', 'recommended_action', 'tenant')
    search_fields = ('product__sku', 'message')


@admin.register(MRPRun)
class MRPRunAdmin(admin.ModelAdmin):
    list_display = ('run_number', 'name', 'run_type', 'status',
                    'started_at', 'finished_at', 'tenant')
    list_filter = ('run_type', 'status', 'tenant')
    search_fields = ('run_number', 'name')


@admin.register(MRPRunResult)
class MRPRunResultAdmin(admin.ModelAdmin):
    list_display = ('run', 'total_planned_orders', 'total_pr_suggestions',
                    'total_exceptions', 'late_orders_count', 'coverage_pct',
                    'computed_at')
