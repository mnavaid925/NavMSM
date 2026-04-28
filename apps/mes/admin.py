from django.contrib import admin

from .models import (
    AndonAlert, MESWorkOrder, MESWorkOrderOperation, OperatorTimeLog,
    ProductionReport, ShopFloorOperator, WorkInstruction,
    WorkInstructionAcknowledgement, WorkInstructionVersion,
)


class MESWorkOrderOperationInline(admin.TabularInline):
    model = MESWorkOrderOperation
    extra = 0
    fields = ('sequence', 'operation_name', 'work_center', 'status',
              'planned_minutes', 'actual_minutes', 'total_good_qty',
              'total_scrap_qty')
    readonly_fields = ('sequence', 'operation_name', 'work_center',
                       'planned_minutes', 'actual_minutes',
                       'total_good_qty', 'total_scrap_qty')


@admin.register(MESWorkOrder)
class MESWorkOrderAdmin(admin.ModelAdmin):
    list_display = ('wo_number', 'product', 'quantity_to_build',
                    'quantity_completed', 'status', 'priority', 'tenant')
    list_filter = ('status', 'priority', 'tenant')
    search_fields = ('wo_number', 'product__sku')
    inlines = [MESWorkOrderOperationInline]


@admin.register(MESWorkOrderOperation)
class MESWorkOrderOperationAdmin(admin.ModelAdmin):
    list_display = ('work_order', 'sequence', 'operation_name', 'work_center',
                    'status', 'planned_minutes', 'actual_minutes',
                    'total_good_qty', 'total_scrap_qty', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('work_order__wo_number', 'operation_name')


@admin.register(ShopFloorOperator)
class ShopFloorOperatorAdmin(admin.ModelAdmin):
    list_display = ('badge_number', 'user', 'default_work_center', 'is_active', 'tenant')
    list_filter = ('is_active', 'tenant')
    search_fields = ('badge_number', 'user__username', 'user__email')


@admin.register(OperatorTimeLog)
class OperatorTimeLogAdmin(admin.ModelAdmin):
    list_display = ('operator', 'action', 'work_order_operation', 'recorded_at', 'tenant')
    list_filter = ('action', 'tenant')
    search_fields = ('operator__badge_number',)
    readonly_fields = ('operator', 'action', 'work_order_operation',
                       'recorded_at', 'notes', 'tenant')

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(ProductionReport)
class ProductionReportAdmin(admin.ModelAdmin):
    list_display = ('work_order_operation', 'good_qty', 'scrap_qty', 'rework_qty',
                    'scrap_reason', 'reported_by', 'reported_at', 'tenant')
    list_filter = ('scrap_reason', 'tenant')
    search_fields = ('work_order_operation__work_order__wo_number',)


@admin.register(AndonAlert)
class AndonAlertAdmin(admin.ModelAdmin):
    list_display = ('alert_number', 'alert_type', 'severity', 'title',
                    'work_center', 'status', 'raised_at', 'tenant')
    list_filter = ('alert_type', 'severity', 'status', 'tenant')
    search_fields = ('alert_number', 'title', 'message')


class WorkInstructionVersionInline(admin.TabularInline):
    model = WorkInstructionVersion
    extra = 0
    fields = ('version', 'status', 'attachment', 'video_url', 'uploaded_at')
    readonly_fields = ('uploaded_at',)


@admin.register(WorkInstruction)
class WorkInstructionAdmin(admin.ModelAdmin):
    list_display = ('instruction_number', 'title', 'doc_type', 'status',
                    'routing_operation', 'product', 'tenant')
    list_filter = ('doc_type', 'status', 'tenant')
    search_fields = ('instruction_number', 'title')
    inlines = [WorkInstructionVersionInline]


@admin.register(WorkInstructionVersion)
class WorkInstructionVersionAdmin(admin.ModelAdmin):
    list_display = ('instruction', 'version', 'status', 'uploaded_by', 'uploaded_at', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('instruction__instruction_number', 'version')


@admin.register(WorkInstructionAcknowledgement)
class WorkInstructionAcknowledgementAdmin(admin.ModelAdmin):
    list_display = ('instruction', 'instruction_version', 'user',
                    'signature_text', 'acknowledged_at', 'tenant')
    list_filter = ('tenant',)
    search_fields = ('instruction__instruction_number', 'user__username')
    readonly_fields = ('instruction', 'instruction_version', 'user',
                       'signature_text', 'acknowledged_at', 'tenant')

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser
