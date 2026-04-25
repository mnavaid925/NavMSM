from django.contrib import admin

from .models import (
    CADDocument, CADDocumentVersion, ComplianceAuditLog, ComplianceStandard,
    ECOApproval, ECOAttachment, ECOImpactedItem, EngineeringChangeOrder,
    NPIDeliverable, NPIProject, NPIStage, Product, ProductCategory,
    ProductCompliance, ProductRevision, ProductSpecification, ProductVariant,
)


# ---- Product Master Data ----

@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'parent', 'tenant', 'is_active')
    list_filter = ('is_active', 'tenant')
    search_fields = ('code', 'name')


class ProductSpecificationInline(admin.TabularInline):
    model = ProductSpecification
    extra = 0


class ProductRevisionInline(admin.TabularInline):
    model = ProductRevision
    extra = 0


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku', 'name', 'category', 'product_type', 'status', 'tenant')
    list_filter = ('product_type', 'status', 'tenant')
    search_fields = ('sku', 'name')
    inlines = [ProductRevisionInline, ProductSpecificationInline, ProductVariantInline]


admin.site.register(ProductRevision)
admin.site.register(ProductSpecification)
admin.site.register(ProductVariant)


# ---- ECO ----

class ECOImpactedItemInline(admin.TabularInline):
    model = ECOImpactedItem
    extra = 0


class ECOApprovalInline(admin.TabularInline):
    model = ECOApproval
    extra = 0


class ECOAttachmentInline(admin.TabularInline):
    model = ECOAttachment
    extra = 0


@admin.register(EngineeringChangeOrder)
class ECOAdmin(admin.ModelAdmin):
    list_display = ('number', 'title', 'status', 'priority', 'change_type', 'tenant')
    list_filter = ('status', 'priority', 'change_type', 'tenant')
    search_fields = ('number', 'title')
    inlines = [ECOImpactedItemInline, ECOApprovalInline, ECOAttachmentInline]


# ---- CAD ----

class CADDocumentVersionInline(admin.TabularInline):
    model = CADDocumentVersion
    fk_name = 'document'
    extra = 0


@admin.register(CADDocument)
class CADDocumentAdmin(admin.ModelAdmin):
    list_display = ('drawing_number', 'title', 'doc_type', 'product', 'is_active', 'tenant')
    list_filter = ('doc_type', 'is_active', 'tenant')
    search_fields = ('drawing_number', 'title')
    inlines = [CADDocumentVersionInline]


admin.site.register(CADDocumentVersion)


# ---- Compliance ----

@admin.register(ComplianceStandard)
class ComplianceStandardAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'region', 'is_active')
    list_filter = ('region', 'is_active')
    search_fields = ('code', 'name')


@admin.register(ProductCompliance)
class ProductComplianceAdmin(admin.ModelAdmin):
    list_display = (
        'product', 'standard', 'status', 'certification_number',
        'issued_date', 'expiry_date', 'tenant',
    )
    list_filter = ('status', 'standard', 'tenant')
    search_fields = ('certification_number',)


admin.site.register(ComplianceAuditLog)


# ---- NPI ----

class NPIStageInline(admin.TabularInline):
    model = NPIStage
    extra = 0


@admin.register(NPIProject)
class NPIProjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'status', 'current_stage', 'project_manager', 'tenant')
    list_filter = ('status', 'current_stage', 'tenant')
    search_fields = ('code', 'name')
    inlines = [NPIStageInline]


class NPIDeliverableInline(admin.TabularInline):
    model = NPIDeliverable
    extra = 0


@admin.register(NPIStage)
class NPIStageAdmin(admin.ModelAdmin):
    list_display = ('project', 'stage', 'sequence', 'status', 'gate_decision')
    list_filter = ('status', 'gate_decision', 'stage')
    inlines = [NPIDeliverableInline]


admin.site.register(NPIDeliverable)
