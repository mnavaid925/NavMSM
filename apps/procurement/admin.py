from django.contrib import admin

from . import models


@admin.register(models.Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'tenant', 'currency', 'is_active', 'is_approved', 'risk_rating')
    list_filter = ('is_active', 'is_approved', 'risk_rating', 'tenant')
    search_fields = ('code', 'name', 'email', 'tax_id')


@admin.register(models.SupplierContact)
class SupplierContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'supplier', 'role', 'email', 'is_primary')
    list_filter = ('is_primary', 'is_active', 'tenant')
    search_fields = ('name', 'email', 'supplier__code')


class PurchaseOrderLineInline(admin.TabularInline):
    model = models.PurchaseOrderLine
    extra = 0
    fields = ('line_number', 'product', 'description', 'quantity', 'unit_price', 'line_total')
    readonly_fields = ('line_total',)


@admin.register(models.PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('po_number', 'tenant', 'supplier', 'status', 'priority', 'order_date', 'grand_total')
    list_filter = ('status', 'priority', 'tenant')
    search_fields = ('po_number', 'supplier__code', 'supplier__name')
    inlines = [PurchaseOrderLineInline]
    readonly_fields = ('po_number', 'subtotal', 'tax_total', 'discount_total', 'grand_total')


@admin.register(models.PurchaseOrderRevision)
class PurchaseOrderRevisionAdmin(admin.ModelAdmin):
    list_display = ('po', 'revision_number', 'changed_by', 'created_at')
    list_filter = ('tenant',)


@admin.register(models.PurchaseOrderApproval)
class PurchaseOrderApprovalAdmin(admin.ModelAdmin):
    list_display = ('po', 'approver', 'decision', 'decided_at')
    list_filter = ('decision', 'tenant')


class RFQLineInline(admin.TabularInline):
    model = models.RFQLine
    extra = 0


class RFQSupplierInline(admin.TabularInline):
    model = models.RFQSupplier
    extra = 0


@admin.register(models.RequestForQuotation)
class RequestForQuotationAdmin(admin.ModelAdmin):
    list_display = ('rfq_number', 'tenant', 'title', 'status', 'issued_date', 'response_due_date')
    list_filter = ('status', 'tenant')
    search_fields = ('rfq_number', 'title')
    inlines = [RFQLineInline, RFQSupplierInline]


class QuotationLineInline(admin.TabularInline):
    model = models.QuotationLine
    extra = 0


@admin.register(models.SupplierQuotation)
class SupplierQuotationAdmin(admin.ModelAdmin):
    list_display = ('quote_number', 'tenant', 'rfq', 'supplier', 'status', 'grand_total')
    list_filter = ('status', 'tenant')
    inlines = [QuotationLineInline]


@admin.register(models.QuotationAward)
class QuotationAwardAdmin(admin.ModelAdmin):
    list_display = ('rfq', 'quotation', 'awarded_by', 'awarded_at')
    list_filter = ('tenant',)


@admin.register(models.SupplierMetricEvent)
class SupplierMetricEventAdmin(admin.ModelAdmin):
    list_display = ('supplier', 'event_type', 'value', 'posted_at', 'tenant')
    list_filter = ('event_type', 'tenant')
    search_fields = ('supplier__code', 'reference_id')
    readonly_fields = ('posted_at',)


@admin.register(models.SupplierScorecard)
class SupplierScorecardAdmin(admin.ModelAdmin):
    list_display = (
        'supplier', 'period_start', 'period_end',
        'overall_score', 'rank', 'otd_pct', 'quality_rating', 'tenant',
    )
    list_filter = ('tenant',)
    readonly_fields = ('computed_at',)


class SupplierASNLineInline(admin.TabularInline):
    model = models.SupplierASNLine
    extra = 0


@admin.register(models.SupplierASN)
class SupplierASNAdmin(admin.ModelAdmin):
    list_display = ('asn_number', 'tenant', 'purchase_order', 'status', 'ship_date')
    list_filter = ('status', 'tenant')
    inlines = [SupplierASNLineInline]


class SupplierInvoiceLineInline(admin.TabularInline):
    model = models.SupplierInvoiceLine
    extra = 0


@admin.register(models.SupplierInvoice)
class SupplierInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'invoice_number', 'tenant', 'supplier', 'vendor_invoice_number',
        'status', 'invoice_date', 'grand_total',
    )
    list_filter = ('status', 'tenant')
    search_fields = ('invoice_number', 'vendor_invoice_number', 'supplier__code')
    inlines = [SupplierInvoiceLineInline]


class BlanketOrderLineInline(admin.TabularInline):
    model = models.BlanketOrderLine
    extra = 0


@admin.register(models.BlanketOrder)
class BlanketOrderAdmin(admin.ModelAdmin):
    list_display = (
        'bpo_number', 'tenant', 'supplier', 'status',
        'start_date', 'end_date', 'total_committed_value', 'consumed_value',
    )
    list_filter = ('status', 'tenant')
    inlines = [BlanketOrderLineInline]


class ScheduleReleaseLineInline(admin.TabularInline):
    model = models.ScheduleReleaseLine
    extra = 0


@admin.register(models.ScheduleRelease)
class ScheduleReleaseAdmin(admin.ModelAdmin):
    list_display = ('release_number', 'tenant', 'blanket_order', 'status', 'release_date', 'total_amount')
    list_filter = ('status', 'tenant')
    inlines = [ScheduleReleaseLineInline]
