"""Admin registrations for Module 15 - IoT & SCADA Integration."""
from django.contrib import admin

from . import models


@admin.register(models.DeviceProtocol)
class DeviceProtocolAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'default_port', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')


@admin.register(models.DeviceBroker)
class DeviceBrokerAdmin(admin.ModelAdmin):
    list_display = ('broker_number', 'name', 'protocol', 'host', 'port', 'status', 'tenant')
    list_filter = ('status', 'protocol', 'tls_enabled', 'auth_method')
    search_fields = ('broker_number', 'name', 'host')
    readonly_fields = ('broker_number', 'last_heartbeat_at')


@admin.register(models.Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('device_number', 'name', 'broker', 'device_type', 'status', 'last_seen_at', 'tenant')
    list_filter = ('status', 'device_type', 'protocol')
    search_fields = ('device_number', 'name', 'serial_number')
    readonly_fields = ('device_number', 'last_seen_at')


@admin.register(models.DeviceTag)
class DeviceTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'device', 'address', 'data_type', 'unit', 'is_active', 'tenant')
    list_filter = ('data_type', 'is_active')
    search_fields = ('name', 'address')


@admin.register(models.IoTReadingBatch)
class IoTReadingBatchAdmin(admin.ModelAdmin):
    list_display = ('batch_number', 'source_format', 'row_count', 'status', 'ingested_at', 'tenant')
    list_filter = ('source_format', 'status')
    readonly_fields = ('batch_number', 'ingested_at')


@admin.register(models.IoTReading)
class IoTReadingAdmin(admin.ModelAdmin):
    list_display = ('entry_number', 'device_tag', 'timestamp', 'quality', 'source', 'tenant')
    list_filter = ('quality', 'source')
    search_fields = ('entry_number',)
    readonly_fields = ('entry_number', 'timestamp')


@admin.register(models.EdgeProcessor)
class EdgeProcessorAdmin(admin.ModelAdmin):
    list_display = ('name', 'input_tag', 'transform_type', 'window_seconds', 'is_active', 'tenant')
    list_filter = ('transform_type', 'is_active')
    search_fields = ('name',)


@admin.register(models.StreamMetric)
class StreamMetricAdmin(admin.ModelAdmin):
    list_display = ('device_tag', 'latest_value', 'latest_timestamp', 'count_24h', 'tenant')
    readonly_fields = ('latest_value', 'latest_timestamp', 'last_24h_min', 'last_24h_max', 'last_24h_avg', 'count_24h')


@admin.register(models.DigitalTwin)
class DigitalTwinAdmin(admin.ModelAdmin):
    list_display = ('twin_number', 'name', 'twin_type', 'asset', 'status', 'model_version', 'tenant')
    list_filter = ('twin_type', 'status')
    search_fields = ('twin_number', 'name')
    readonly_fields = ('twin_number',)


@admin.register(models.TwinStateAttribute)
class TwinStateAttributeAdmin(admin.ModelAdmin):
    list_display = ('twin', 'name', 'attribute_type', 'unit', 'current_value_at', 'tenant')
    list_filter = ('attribute_type',)
    search_fields = ('name',)


@admin.register(models.TwinSimulationScenario)
class TwinSimulationScenarioAdmin(admin.ModelAdmin):
    list_display = ('scenario_number', 'twin', 'name', 'status', 'run_at', 'tenant')
    list_filter = ('status',)
    readonly_fields = ('scenario_number', 'run_at')


@admin.register(models.TwinStateSnapshot)
class TwinStateSnapshotAdmin(admin.ModelAdmin):
    list_display = ('twin', 'snapshot_at', 'triggered_by', 'tenant')
    list_filter = ('triggered_by',)


@admin.register(models.LossReason)
class LossReasonAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'is_planned', 'is_active', 'tenant')
    list_filter = ('category', 'is_planned', 'is_active')


@admin.register(models.MachineStateLog)
class MachineStateLogAdmin(admin.ModelAdmin):
    list_display = ('asset', 'state', 'started_at', 'ended_at', 'duration_seconds', 'source', 'tenant')
    list_filter = ('state', 'source')
    readonly_fields = ('duration_seconds',)


@admin.register(models.OEEPeriod)
class OEEPeriodAdmin(admin.ModelAdmin):
    list_display = ('period_number', 'asset', 'shift', 'period_date', 'oee_pct', 'tenant')
    list_filter = ('period_date',)
    readonly_fields = (
        'period_number', 'availability_pct', 'performance_pct',
        'quality_pct', 'oee_pct', 'recomputed_at',
    )


@admin.register(models.AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = ('rule_number', 'name', 'condition_type', 'severity', 'is_active', 'tenant')
    list_filter = ('condition_type', 'severity', 'is_active')
    search_fields = ('rule_number', 'name')
    readonly_fields = ('rule_number',)


@admin.register(models.AnomalyDetection)
class AnomalyDetectionAdmin(admin.ModelAdmin):
    list_display = ('detection_number', 'rule', 'severity', 'status', 'detected_at', 'tenant')
    list_filter = ('severity', 'status')
    search_fields = ('detection_number',)
    readonly_fields = ('detection_number', 'detected_at')


@admin.register(models.AlertNotification)
class AlertNotificationAdmin(admin.ModelAdmin):
    list_display = ('detection', 'channel', 'status', 'sent_at', 'tenant')
    list_filter = ('channel', 'status')
