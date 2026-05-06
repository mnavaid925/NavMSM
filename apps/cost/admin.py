from django.contrib import admin

from . import models


@admin.register(models.StandardCostVersion)
class StandardCostVersionAdmin(admin.ModelAdmin):
    list_display = ['version_number', 'name', 'effective_from', 'status', 'tenant']
    list_filter = ['status', 'tenant']
    search_fields = ['version_number', 'name']


@admin.register(models.StandardCost)
class StandardCostAdmin(admin.ModelAdmin):
    list_display = ['version', 'product', 'total_cost', 'source']
    list_filter = ['source', 'tenant']
    search_fields = ['product__sku', 'version__version_number']


@admin.register(models.StandardCostHistory)
class StandardCostHistoryAdmin(admin.ModelAdmin):
    list_display = ['cost', 'field', 'old_value', 'new_value', 'changed_at']
    list_filter = ['field']


@admin.register(models.CostDriver)
class CostDriverAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'unit_of_measure', 'is_active', 'tenant']
    list_filter = ['is_active', 'tenant']
    search_fields = ['code', 'name']


@admin.register(models.OverheadPool)
class OverheadPoolAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'pool_type', 'allocation_method', 'is_active', 'tenant']
    list_filter = ['pool_type', 'allocation_method', 'is_active']
    search_fields = ['code', 'name']


@admin.register(models.AccountingPeriod)
class AccountingPeriodAdmin(admin.ModelAdmin):
    list_display = ['period_number', 'name', 'period_type', 'start_date', 'end_date', 'status', 'tenant']
    list_filter = ['status', 'period_type', 'tenant']
    search_fields = ['period_number', 'name']


@admin.register(models.OverheadRate)
class OverheadRateAdmin(admin.ModelAdmin):
    list_display = ['pool', 'period', 'driver', 'budgeted_amount', 'rate_per_driver_unit']
    list_filter = ['period', 'pool']


@admin.register(models.OverheadActualPool)
class OverheadActualPoolAdmin(admin.ModelAdmin):
    list_display = ['pool', 'period', 'actual_amount', 'last_updated_at']
    list_filter = ['period', 'pool']


@admin.register(models.DriverActuals)
class DriverActualsAdmin(admin.ModelAdmin):
    list_display = ['driver', 'period', 'cost_center', 'production_order', 'quantity', 'recorded_at']
    list_filter = ['period', 'driver']


@admin.register(models.OverheadAllocation)
class OverheadAllocationAdmin(admin.ModelAdmin):
    list_display = ['allocation_number', 'pool', 'period', 'applied_amount', 'is_reversed']
    list_filter = ['period', 'pool', 'is_reversed']
    search_fields = ['allocation_number']


@admin.register(models.JobCost)
class JobCostAdmin(admin.ModelAdmin):
    list_display = ['job_number', 'production_order', 'status', 'wip_balance', 'tenant']
    list_filter = ['status', 'tenant']
    search_fields = ['job_number']


@admin.register(models.WIPEntry)
class WIPEntryAdmin(admin.ModelAdmin):
    list_display = ['entry_number', 'job', 'entry_type', 'amount', 'entry_date', 'is_reversal']
    list_filter = ['entry_type', 'is_reversal']
    search_fields = ['entry_number']


@admin.register(models.ActualCost)
class ActualCostAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'as_of_date', 'total_cost', 'is_locked']
    list_filter = ['is_locked']


@admin.register(models.CostVariance)
class CostVarianceAdmin(admin.ModelAdmin):
    list_display = ['variance_number', 'production_order', 'version', 'total_variance', 'analyzed_at']
    search_fields = ['variance_number']


@admin.register(models.COGMReport)
class COGMReportAdmin(admin.ModelAdmin):
    list_display = ['report_number', 'period', 'cogm', 'generated_at']
    search_fields = ['report_number']


@admin.register(models.GrossMarginReport)
class GrossMarginReportAdmin(admin.ModelAdmin):
    list_display = ['period', 'product', 'units_completed', 'gross_margin', 'margin_percent']
    list_filter = ['period']


@admin.register(models.PlantPnLReport)
class PlantPnLReportAdmin(admin.ModelAdmin):
    list_display = ['period', 'revenue', 'cogm', 'operating_income', 'generated_at']
    list_filter = ['period']
