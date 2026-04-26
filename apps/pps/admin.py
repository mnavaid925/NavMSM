from django.contrib import admin

from .models import (
    CapacityCalendar, CapacityLoad, DemandForecast, MasterProductionSchedule,
    MPSLine, OptimizationObjective, OptimizationResult, OptimizationRun,
    ProductionOrder, Routing, RoutingOperation, ScenarioChange,
    ScenarioResult, Scenario, ScheduledOperation, WorkCenter,
)


class MPSLineInline(admin.TabularInline):
    model = MPSLine
    fk_name = 'mps'
    extra = 0
    fields = ('product', 'period_start', 'period_end', 'forecast_qty',
              'firm_planned_qty', 'scheduled_qty', 'available_to_promise')


@admin.register(DemandForecast)
class DemandForecastAdmin(admin.ModelAdmin):
    list_display = ('product', 'period_start', 'period_end', 'forecast_qty',
                    'source', 'confidence_pct', 'tenant')
    list_filter = ('source', 'tenant')
    search_fields = ('product__sku',)


@admin.register(MasterProductionSchedule)
class MasterProductionScheduleAdmin(admin.ModelAdmin):
    list_display = ('mps_number', 'name', 'horizon_start', 'horizon_end',
                    'time_bucket', 'status', 'tenant')
    list_filter = ('status', 'time_bucket', 'tenant')
    search_fields = ('mps_number', 'name')
    inlines = [MPSLineInline]


@admin.register(MPSLine)
class MPSLineAdmin(admin.ModelAdmin):
    list_display = ('mps', 'product', 'period_start', 'forecast_qty',
                    'firm_planned_qty', 'scheduled_qty')
    search_fields = ('mps__mps_number', 'product__sku')


@admin.register(WorkCenter)
class WorkCenterAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'work_center_type', 'capacity_per_hour',
                    'efficiency_pct', 'cost_per_hour', 'is_active', 'tenant')
    list_filter = ('work_center_type', 'is_active', 'tenant')
    search_fields = ('code', 'name')


@admin.register(CapacityCalendar)
class CapacityCalendarAdmin(admin.ModelAdmin):
    list_display = ('work_center', 'day_of_week', 'shift_start', 'shift_end', 'is_working')
    list_filter = ('day_of_week', 'is_working', 'work_center')


@admin.register(CapacityLoad)
class CapacityLoadAdmin(admin.ModelAdmin):
    list_display = ('work_center', 'period_date', 'planned_minutes',
                    'available_minutes', 'utilization_pct', 'is_bottleneck',
                    'computed_at')
    list_filter = ('is_bottleneck', 'work_center')


class RoutingOperationInline(admin.TabularInline):
    model = RoutingOperation
    extra = 0
    fields = ('sequence', 'operation_name', 'work_center', 'setup_minutes',
              'run_minutes_per_unit', 'queue_minutes', 'move_minutes')


@admin.register(Routing)
class RoutingAdmin(admin.ModelAdmin):
    list_display = ('routing_number', 'product', 'version', 'is_default',
                    'status', 'tenant')
    list_filter = ('status', 'is_default', 'tenant')
    search_fields = ('routing_number', 'product__sku')
    inlines = [RoutingOperationInline]


@admin.register(RoutingOperation)
class RoutingOperationAdmin(admin.ModelAdmin):
    list_display = ('routing', 'sequence', 'operation_name', 'work_center',
                    'setup_minutes', 'run_minutes_per_unit')
    list_filter = ('work_center',)
    search_fields = ('operation_name',)


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'product', 'quantity', 'status',
                    'priority', 'scheduling_method', 'scheduled_start',
                    'scheduled_end', 'tenant')
    list_filter = ('status', 'priority', 'scheduling_method', 'tenant')
    search_fields = ('order_number', 'product__sku')


@admin.register(ScheduledOperation)
class ScheduledOperationAdmin(admin.ModelAdmin):
    list_display = ('production_order', 'sequence', 'work_center',
                    'planned_start', 'planned_end', 'status')
    list_filter = ('status', 'work_center')
    search_fields = ('production_order__order_number',)


class ScenarioChangeInline(admin.TabularInline):
    model = ScenarioChange
    extra = 0
    fields = ('sequence', 'change_type', 'target_ref', 'payload', 'notes')


@admin.register(Scenario)
class ScenarioAdmin(admin.ModelAdmin):
    list_display = ('name', 'base_mps', 'status', 'created_by',
                    'ran_at', 'applied_at', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('name',)
    inlines = [ScenarioChangeInline]


@admin.register(ScenarioChange)
class ScenarioChangeAdmin(admin.ModelAdmin):
    list_display = ('scenario', 'sequence', 'change_type', 'target_ref')
    list_filter = ('change_type',)
    search_fields = ('scenario__name', 'target_ref')


@admin.register(ScenarioResult)
class ScenarioResultAdmin(admin.ModelAdmin):
    list_display = ('scenario', 'on_time_pct', 'total_load_minutes',
                    'total_idle_minutes', 'bottleneck_count', 'computed_at')


@admin.register(OptimizationObjective)
class OptimizationObjectiveAdmin(admin.ModelAdmin):
    list_display = ('name', 'weight_changeovers', 'weight_idle',
                    'weight_lateness', 'weight_priority', 'is_default', 'tenant')
    list_filter = ('is_default', 'tenant')
    search_fields = ('name',)


@admin.register(OptimizationRun)
class OptimizationRunAdmin(admin.ModelAdmin):
    list_display = ('name', 'mps', 'objective', 'status',
                    'started_at', 'finished_at', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('name', 'mps__mps_number')


@admin.register(OptimizationResult)
class OptimizationResultAdmin(admin.ModelAdmin):
    list_display = ('run', 'before_changeovers', 'after_changeovers',
                    'before_lateness', 'after_lateness', 'improvement_pct')
