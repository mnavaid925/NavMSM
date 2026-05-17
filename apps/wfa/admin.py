"""Module 20 - WFA admin registrations.

Append-only ledger models (ProcessActivity, ApprovalActionLog,
NotificationDelivery, SMSDelivery, WebhookOutboxEntry) ship with
``readonly_fields = '__all__'`` so the audit trail cannot be edited
from /admin/.
"""
from django.contrib import admin

from . import models as M


@admin.register(M.ProcessCategory)
class ProcessCategoryAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'name', 'is_active')
    list_filter = ('is_active', 'tenant')
    search_fields = ('code', 'name')


@admin.register(M.ProcessDefinition)
class ProcessDefinitionAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'name', 'version', 'status', 'is_default')
    list_filter = ('status', 'is_default', 'tenant')
    search_fields = ('code', 'name')
    autocomplete_fields = ('category', 'owner')


@admin.register(M.ProcessNode)
class ProcessNodeAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'definition', 'node_key', 'node_type', 'order')
    list_filter = ('node_type', 'tenant')
    search_fields = ('node_key', 'name')
    autocomplete_fields = ('definition',)


@admin.register(M.ProcessTransition)
class ProcessTransitionAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'definition', 'from_node', 'to_node', 'name')
    list_filter = ('tenant',)
    search_fields = ('name',)
    autocomplete_fields = ('definition', 'from_node', 'to_node')


@admin.register(M.ProcessInstance)
class ProcessInstanceAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'definition', 'status', 'started_at', 'completed_at')
    list_filter = ('status', 'tenant')
    search_fields = ('code',)
    autocomplete_fields = ('definition', 'started_by', 'current_node')


@admin.register(M.ProcessVariable)
class ProcessVariableAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'instance', 'name', 'value_type', 'value_text')
    list_filter = ('value_type', 'tenant')
    search_fields = ('name',)


@admin.register(M.ProcessActivity)
class ProcessActivityAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'instance', 'node', 'event', 'actor', 'recorded_at')
    list_filter = ('event', 'tenant')
    search_fields = ('instance__code',)
    readonly_fields = tuple(
        f.name for f in M.ProcessActivity._meta.fields
    )


@admin.register(M.ApprovalPolicy)
class ApprovalPolicyAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'name', 'applies_to_type', 'is_active')
    list_filter = ('is_active', 'tenant')
    search_fields = ('code', 'name', 'applies_to_type')


@admin.register(M.ApprovalLevel)
class ApprovalLevelAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'policy', 'level_no', 'name', 'approver_role', 'sla_hours')
    list_filter = ('approver_role', 'tenant')
    search_fields = ('name',)
    autocomplete_fields = ('policy',)


@admin.register(M.ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'policy', 'subject', 'status', 'current_level_no', 'due_at')
    list_filter = ('status', 'tenant')
    search_fields = ('code', 'subject')
    autocomplete_fields = ('policy', 'requested_by')


@admin.register(M.ApprovalDelegation)
class ApprovalDelegationAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'delegator', 'delegate', 'policy', 'starts_at', 'ends_at', 'is_active')
    list_filter = ('is_active', 'tenant')
    autocomplete_fields = ('delegator', 'delegate', 'policy')


@admin.register(M.ApprovalActionLog)
class ApprovalActionLogAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'request', 'level_no', 'decision', 'actor', 'decided_at')
    list_filter = ('decision', 'tenant')
    search_fields = ('request__code',)
    readonly_fields = tuple(
        f.name for f in M.ApprovalActionLog._meta.fields
    )


@admin.register(M.EscalationRule)
class EscalationRuleAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'policy', 'level_no', 'trigger_hours_overdue', 'escalate_to_role')
    list_filter = ('escalate_to_role', 'tenant')
    autocomplete_fields = ('policy',)


@admin.register(M.NotificationChannel)
class NotificationChannelAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'name', 'is_active')
    list_filter = ('code', 'is_active', 'tenant')


@admin.register(M.NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'name', 'event_type', 'is_active')
    list_filter = ('is_active', 'tenant')
    search_fields = ('code', 'name', 'event_type')


@admin.register(M.NotificationRule)
class NotificationRuleAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'name', 'event_type', 'template', 'is_active')
    list_filter = ('is_active', 'tenant')
    search_fields = ('code', 'name', 'event_type')
    autocomplete_fields = ('template',)


@admin.register(M.Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'event_type', 'recipient', 'status', 'triggered_at')
    list_filter = ('status', 'tenant')
    search_fields = ('code', 'subject')
    autocomplete_fields = ('rule', 'recipient')


@admin.register(M.NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'notification', 'channel', 'status', 'attempted_at')
    list_filter = ('status', 'tenant')
    readonly_fields = tuple(
        f.name for f in M.NotificationDelivery._meta.fields
    )


@admin.register(M.SMSDelivery)
class SMSDeliveryAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'to_phone', 'status', 'sent_at')
    list_filter = ('status', 'tenant')
    search_fields = ('to_phone',)
    readonly_fields = tuple(
        f.name for f in M.SMSDelivery._meta.fields
    )


@admin.register(M.Connector)
class ConnectorAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'name', 'connector_type', 'is_active')
    list_filter = ('connector_type', 'is_active', 'tenant')
    search_fields = ('code', 'name')


@admin.register(M.ConnectorEndpoint)
class ConnectorEndpointAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'connector', 'name', 'method', 'is_active')
    list_filter = ('method', 'is_active', 'tenant')
    search_fields = ('name', 'path')
    autocomplete_fields = ('connector',)


@admin.register(M.IntegrationFlow)
class IntegrationFlowAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'name', 'trigger_type', 'is_active')
    list_filter = ('trigger_type', 'is_active', 'tenant')
    search_fields = ('code', 'name')


@admin.register(M.FlowStep)
class FlowStepAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'flow', 'step_no', 'name', 'step_type')
    list_filter = ('step_type', 'tenant')
    autocomplete_fields = ('flow', 'endpoint')


@admin.register(M.IntegrationRun)
class IntegrationRunAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'flow', 'status', 'started_at', 'finished_at')
    list_filter = ('status', 'tenant')
    search_fields = ('code',)
    autocomplete_fields = ('flow', 'triggered_by')


@admin.register(M.WebhookOutboxEntry)
class WebhookOutboxEntryAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'target_url', 'status', 'attempts', 'last_attempt_at')
    list_filter = ('status', 'tenant')
    readonly_fields = tuple(
        f.name for f in M.WebhookOutboxEntry._meta.fields
    )


@admin.register(M.ProcessMetric)
class ProcessMetricAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'instance', 'metric_type', 'value_seconds', 'recorded_at')
    list_filter = ('metric_type', 'tenant')


@admin.register(M.BottleneckAnalysis)
class BottleneckAnalysisAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'definition', 'period_start', 'period_end', 'severity', 'avg_wait_seconds')
    list_filter = ('severity', 'tenant')
    search_fields = ('code',)
    autocomplete_fields = ('definition', 'bottleneck_node')


@admin.register(M.ProcessOptimizationSuggestion)
class ProcessOptimizationSuggestionAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'definition', 'suggestion_type', 'status', 'expected_savings_pct')
    list_filter = ('suggestion_type', 'status', 'tenant')
    autocomplete_fields = ('definition', 'analysis')


@admin.register(M.CycleTimeReport)
class CycleTimeReportAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'code', 'definition', 'period_start', 'period_end', 'instance_count', 'avg_cycle_seconds')
    list_filter = ('tenant',)
    autocomplete_fields = ('definition',)
