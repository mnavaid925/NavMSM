from django.contrib import admin

from .models import (
    AlternateMaterial, BillOfMaterials, BOMCostRollup, BOMLine, BOMRevision,
    BOMSyncLog, BOMSyncMap, CostElement, SubstitutionRule,
)


class BOMLineInline(admin.TabularInline):
    model = BOMLine
    fk_name = 'bom'
    extra = 0
    fields = ('sequence', 'parent_line', 'component', 'quantity', 'unit_of_measure',
              'scrap_percent', 'is_phantom', 'reference_designator')


@admin.register(BillOfMaterials)
class BillOfMaterialsAdmin(admin.ModelAdmin):
    list_display = ('bom_number', 'product', 'bom_type', 'version', 'revision', 'status', 'is_default', 'tenant')
    list_filter = ('bom_type', 'status', 'is_default', 'tenant')
    search_fields = ('bom_number', 'name', 'product__sku')
    inlines = [BOMLineInline]


@admin.register(BOMLine)
class BOMLineAdmin(admin.ModelAdmin):
    list_display = ('bom', 'sequence', 'component', 'quantity', 'unit_of_measure', 'is_phantom')
    list_filter = ('is_phantom', 'unit_of_measure')
    search_fields = ('component__sku', 'bom__bom_number')


@admin.register(BOMRevision)
class BOMRevisionAdmin(admin.ModelAdmin):
    list_display = ('bom', 'version', 'revision', 'revision_type', 'effective_from', 'changed_by', 'tenant')
    list_filter = ('revision_type', 'tenant')
    search_fields = ('bom__bom_number',)


@admin.register(AlternateMaterial)
class AlternateMaterialAdmin(admin.ModelAdmin):
    list_display = ('bom_line', 'alternate_component', 'priority', 'substitution_type', 'approval_status', 'tenant')
    list_filter = ('approval_status', 'substitution_type', 'tenant')
    search_fields = ('alternate_component__sku',)


@admin.register(SubstitutionRule)
class SubstitutionRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'original_component', 'substitute_component', 'requires_approval', 'is_active', 'tenant')
    list_filter = ('is_active', 'requires_approval', 'tenant')
    search_fields = ('name', 'original_component__sku', 'substitute_component__sku')


@admin.register(CostElement)
class CostElementAdmin(admin.ModelAdmin):
    list_display = ('product', 'cost_type', 'unit_cost', 'currency', 'effective_date', 'source', 'tenant')
    list_filter = ('cost_type', 'source', 'tenant')
    search_fields = ('product__sku',)


@admin.register(BOMCostRollup)
class BOMCostRollupAdmin(admin.ModelAdmin):
    list_display = ('bom', 'total_cost', 'currency', 'computed_at', 'tenant')
    list_filter = ('tenant',)
    search_fields = ('bom__bom_number',)


@admin.register(BOMSyncMap)
class BOMSyncMapAdmin(admin.ModelAdmin):
    list_display = ('source_bom', 'target_bom', 'sync_status', 'last_synced_at', 'tenant')
    list_filter = ('sync_status', 'tenant')
    search_fields = ('source_bom__bom_number', 'target_bom__bom_number')


admin.site.register(BOMSyncLog)
