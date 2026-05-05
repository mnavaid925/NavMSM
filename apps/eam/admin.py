from django.contrib import admin

from . import models


@admin.register(models.AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'tenant', 'is_active')
    list_filter = ('is_active', 'tenant')
    search_fields = ('name',)


class AssetSparePartInline(admin.TabularInline):
    model = models.AssetSparePart
    extra = 0


@admin.register(models.Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('tag', 'name', 'category', 'criticality', 'status', 'tenant', 'is_active')
    list_filter = ('status', 'criticality', 'is_active', 'tenant')
    search_fields = ('tag', 'name', 'serial_number', 'model_number')
    readonly_fields = ('tag',)
    inlines = [AssetSparePartInline]


@admin.register(models.AssetSparePart)
class AssetSparePartAdmin(admin.ModelAdmin):
    list_display = ('asset', 'product', 'recommended_min_qty', 'tenant')
    list_filter = ('tenant',)
    search_fields = ('asset__tag', 'product__sku')


@admin.register(models.AssetMeterReading)
class AssetMeterReadingAdmin(admin.ModelAdmin):
    list_display = ('asset', 'meter_type', 'reading_value', 'recorded_at', 'tenant')
    list_filter = ('meter_type', 'tenant')
    search_fields = ('asset__tag',)
    readonly_fields = ('recorded_at',)


@admin.register(models.AssetDocument)
class AssetDocumentAdmin(admin.ModelAdmin):
    list_display = ('asset', 'name', 'doc_type', 'uploaded_by', 'tenant')
    list_filter = ('doc_type', 'tenant')


class MaintenanceTaskInline(admin.TabularInline):
    model = models.MaintenanceTask
    extra = 0


@admin.register(models.MaintenancePlan)
class MaintenancePlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'asset', 'trigger_type', 'is_active', 'next_due_at', 'tenant')
    list_filter = ('trigger_type', 'is_active', 'tenant')
    search_fields = ('name', 'asset__tag')
    inlines = [MaintenanceTaskInline]


@admin.register(models.MaintenanceTask)
class MaintenanceTaskAdmin(admin.ModelAdmin):
    list_display = ('plan', 'sequence', 'description', 'is_critical', 'tenant')
    list_filter = ('is_critical', 'tenant')


class PMTaskCompletionInline(admin.TabularInline):
    model = models.PMTaskCompletion
    extra = 0


@admin.register(models.PMSchedule)
class PMScheduleAdmin(admin.ModelAdmin):
    list_display = (
        'schedule_number', 'plan', 'scheduled_date', 'status', 'assignee', 'tenant',
    )
    list_filter = ('status', 'tenant')
    search_fields = ('schedule_number', 'plan__name')
    readonly_fields = ('schedule_number',)
    inlines = [PMTaskCompletionInline]


@admin.register(models.PMTaskCompletion)
class PMTaskCompletionAdmin(admin.ModelAdmin):
    list_display = ('pm_schedule', 'task', 'result', 'completed_at', 'tenant')
    list_filter = ('result', 'tenant')


@admin.register(models.ConditionMonitoringPoint)
class ConditionMonitoringPointAdmin(admin.ModelAdmin):
    list_display = ('asset', 'name', 'parameter', 'unit', 'is_active', 'tenant')
    list_filter = ('parameter', 'is_active', 'tenant')


@admin.register(models.ConditionReading)
class ConditionReadingAdmin(admin.ModelAdmin):
    list_display = ('point', 'reading_value', 'status', 'recorded_at', 'tenant')
    list_filter = ('status', 'tenant')
    readonly_fields = ('recorded_at',)


@admin.register(models.FailurePrediction)
class FailurePredictionAdmin(admin.ModelAdmin):
    list_display = ('asset', 'summary', 'confidence_pct', 'status', 'predicted_failure_date', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('asset__tag', 'summary')


class MWOLaborLogInline(admin.TabularInline):
    model = models.MWOLaborLog
    extra = 0


class MWOMaterialLogInline(admin.TabularInline):
    model = models.MWOMaterialLog
    extra = 0


@admin.register(models.MaintenanceWorkOrder)
class MaintenanceWorkOrderAdmin(admin.ModelAdmin):
    list_display = (
        'mwo_number', 'asset', 'wo_type', 'priority', 'status',
        'reported_at', 'completed_at', 'tenant',
    )
    list_filter = ('status', 'wo_type', 'priority', 'tenant')
    search_fields = ('mwo_number', 'asset__tag', 'title')
    readonly_fields = ('mwo_number', 'downtime_minutes')
    inlines = [MWOLaborLogInline, MWOMaterialLogInline]


@admin.register(models.MWOLaborLog)
class MWOLaborLogAdmin(admin.ModelAdmin):
    list_display = ('mwo', 'technician', 'started_at', 'minutes', 'total_cost', 'tenant')
    list_filter = ('tenant',)


@admin.register(models.MWOMaterialLog)
class MWOMaterialLogAdmin(admin.ModelAdmin):
    list_display = ('mwo', 'product', 'quantity', 'unit_cost', 'total_cost', 'tenant')
    list_filter = ('tenant',)


@admin.register(models.DowntimeEvent)
class DowntimeEventAdmin(admin.ModelAdmin):
    list_display = ('asset', 'mwo', 'started_at', 'ended_at', 'minutes', 'downtime_type', 'tenant')
    list_filter = ('downtime_type', 'tenant')


class MoldCavityHistoryInline(admin.TabularInline):
    model = models.MoldCavityHistory
    extra = 0


@admin.register(models.Tool)
class ToolAdmin(admin.ModelAdmin):
    list_display = (
        'tool_id', 'name', 'tool_type', 'status',
        'current_cycles', 'expected_life_cycles', 'tenant',
    )
    list_filter = ('tool_type', 'status', 'is_active', 'tenant')
    search_fields = ('tool_id', 'name')
    readonly_fields = ('tool_id', 'current_cycles', 'current_hours')
    inlines = [MoldCavityHistoryInline]


@admin.register(models.ToolUsageLog)
class ToolUsageLogAdmin(admin.ModelAdmin):
    list_display = ('tool', 'used_at', 'cycles_added', 'hours_added', 'operator', 'tenant')
    list_filter = ('tenant',)


@admin.register(models.ToolMaintenanceRecord)
class ToolMaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = ('tool', 'record_type', 'performed_at', 'cost', 'tenant')
    list_filter = ('record_type', 'tenant')


@admin.register(models.MoldCavityHistory)
class MoldCavityHistoryAdmin(admin.ModelAdmin):
    list_display = ('tool', 'cavity_number', 'cycles', 'defect_count', 'status', 'tenant')
    list_filter = ('status', 'tenant')
