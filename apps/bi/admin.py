"""Admin registrations for Module 16 - Business Intelligence & Analytics."""
from django.contrib import admin

from . import models


@admin.register(models.KPIDefinition)
class KPIDefinitionAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'unit', 'direction', 'target_value', 'is_active', 'tenant')
    list_filter = ('direction', 'is_active')
    search_fields = ('code', 'name')


@admin.register(models.KPIDashboard)
class KPIDashboardAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'owner', 'is_shared', 'default_period', 'auto_refresh_minutes', 'tenant')
    list_filter = ('is_shared', 'default_period')
    search_fields = ('name', 'slug')


@admin.register(models.KPIWidget)
class KPIWidgetAdmin(admin.ModelAdmin):
    list_display = ('dashboard', 'kpi_definition', 'chart_type', 'position', 'compare_to_previous', 'tenant')
    list_filter = ('chart_type', 'compare_to_previous')


@admin.register(models.KPISnapshot)
class KPISnapshotAdmin(admin.ModelAdmin):
    list_display = (
        'kpi_definition', 'period_start', 'period_end', 'scope_type',
        'scope_pk', 'value', 'status', 'computed_at', 'tenant',
    )
    list_filter = ('status', 'scope_type', 'kpi_definition__code')
    readonly_fields = ('computed_at',)


@admin.register(models.ReportDataSource)
class ReportDataSourceAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'model_label', 'is_active', 'tenant')
    list_filter = ('is_active',)
    search_fields = ('code', 'name', 'model_label')


@admin.register(models.ReportDefinition)
class ReportDefinitionAdmin(admin.ModelAdmin):
    list_display = ('report_number', 'name', 'data_source', 'is_shared', 'row_limit', 'tenant')
    list_filter = ('is_shared',)
    search_fields = ('report_number', 'name')
    readonly_fields = ('report_number',)


@admin.register(models.ReportField)
class ReportFieldAdmin(admin.ModelAdmin):
    list_display = ('report', 'field_name', 'display_name', 'aggregation', 'position', 'tenant')
    list_filter = ('aggregation',)


@admin.register(models.ReportFilter)
class ReportFilterAdmin(admin.ModelAdmin):
    list_display = ('report', 'field_name', 'operator', 'value', 'position', 'tenant')
    list_filter = ('operator',)


@admin.register(models.ReportRun)
class ReportRunAdmin(admin.ModelAdmin):
    list_display = ('run_number', 'report', 'status', 'row_count', 'duration_ms', 'run_at', 'tenant')
    list_filter = ('status',)
    readonly_fields = ('run_number', 'run_at')


@admin.register(models.PredictiveModel)
class PredictiveModelAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'lookback_days', 'forecast_horizon_days', 'is_active', 'tenant')
    list_filter = ('code', 'is_active')
    search_fields = ('code', 'name')


@admin.register(models.PredictionRun)
class PredictionRunAdmin(admin.ModelAdmin):
    list_display = (
        'run_number', 'predictive_model', 'status', 'result_count',
        'started_at', 'finished_at', 'tenant',
    )
    list_filter = ('status', 'predictive_model__code')
    readonly_fields = ('run_number', 'started_at')


@admin.register(models.PredictionResult)
class PredictionResultAdmin(admin.ModelAdmin):
    list_display = ('run', 'target_type', 'target_pk', 'period_date', 'predicted_value', 'confidence_pct', 'tenant')
    list_filter = ('target_type',)


@admin.register(models.TrendAnalysis)
class TrendAnalysisAdmin(admin.ModelAdmin):
    list_display = ('trend_number', 'name', 'source_metric', 'direction', 'r_squared', 'computed_at', 'tenant')
    list_filter = ('source_metric', 'direction')
    readonly_fields = ('trend_number', 'computed_at')


@admin.register(models.DataMart)
class DataMartAdmin(admin.ModelAdmin):
    list_display = (
        'mart_number', 'code', 'name', 'refresh_frequency', 'is_active',
        'last_refreshed_at', 'last_row_count', 'tenant',
    )
    list_filter = ('refresh_frequency', 'is_active')
    search_fields = ('mart_number', 'code', 'name')
    readonly_fields = ('mart_number',)


@admin.register(models.DataMartColumn)
class DataMartColumnAdmin(admin.ModelAdmin):
    list_display = ('data_mart', 'code', 'display_name', 'data_type', 'is_dimension', 'is_measure', 'tenant')
    list_filter = ('data_type', 'is_dimension', 'is_measure')


@admin.register(models.DataMartSnapshot)
class DataMartSnapshotAdmin(admin.ModelAdmin):
    list_display = ('data_mart', 'snapshot_at', 'row_count', 'duration_ms', 'triggered_by', 'tenant')
    list_filter = ('triggered_by',)


@admin.register(models.DataMartRow)
class DataMartRowAdmin(admin.ModelAdmin):
    list_display = ('data_mart', 'snapshot', 'measure_total', 'tenant')
    raw_id_fields = ('snapshot', 'data_mart')


@admin.register(models.ReportSchedule)
class ReportScheduleAdmin(admin.ModelAdmin):
    list_display = (
        'schedule_number', 'name', 'frequency', 'format', 'status',
        'next_run_at', 'last_run_at', 'tenant',
    )
    list_filter = ('frequency', 'format', 'status')
    search_fields = ('schedule_number', 'name')
    readonly_fields = ('schedule_number', 'last_run_at', 'last_status')


@admin.register(models.ReportRecipient)
class ReportRecipientAdmin(admin.ModelAdmin):
    list_display = ('schedule', 'name', 'email', 'is_active', 'notify_on_failure', 'tenant')
    list_filter = ('is_active', 'notify_on_failure')
    search_fields = ('email', 'name')


@admin.register(models.ReportExport)
class ReportExportAdmin(admin.ModelAdmin):
    list_display = (
        'export_number', 'report', 'dashboard', 'format', 'status',
        'row_count', 'generated_at', 'tenant',
    )
    list_filter = ('format', 'status')
    readonly_fields = ('export_number', 'generated_at', 'file_size_bytes')


@admin.register(models.ReportDelivery)
class ReportDeliveryAdmin(admin.ModelAdmin):
    list_display = ('delivery_number', 'schedule', 'recipient', 'status', 'attempted_at', 'delivered_at', 'tenant')
    list_filter = ('status',)
    readonly_fields = ('delivery_number', 'attempted_at', 'delivered_at', 'message_id')
