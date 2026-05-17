"""Django admin registration for Module 17 - Sales."""
from django.contrib import admin

from .models import (
    ATPCalculation,
    CTPCalculation,
    CommunicationLog,
    Customer,
    CustomerCategory,
    CustomerContact,
    CustomerDocument,
    DeliveryRoute,
    OrderPromise,
    PriceList,
    PriceListItem,
    ProofOfDelivery,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderApprovalLog,
    SalesOrderLine,
    SalesOrderRevision,
    Shipment,
    ShipmentLine,
)


@admin.register(CustomerCategory)
class CustomerCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'parent', 'is_active', 'tenant')
    list_filter = ('is_active', 'tenant')
    search_fields = ('name', 'code')


class PriceListItemInline(admin.TabularInline):
    model = PriceListItem
    extra = 0
    autocomplete_fields = ('product',)


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'currency', 'is_default', 'is_active', 'tenant')
    list_filter = ('is_default', 'is_active', 'currency', 'tenant')
    search_fields = ('code', 'name')
    inlines = [PriceListItemInline]


@admin.register(PriceListItem)
class PriceListItemAdmin(admin.ModelAdmin):
    list_display = ('price_list', 'product', 'unit_price', 'min_qty', 'discount_pct')
    list_filter = ('price_list', 'tenant')
    search_fields = ('price_list__name', 'product__name', 'product__sku')
    autocomplete_fields = ('product', 'price_list')


class CustomerContactInline(admin.TabularInline):
    model = CustomerContact
    extra = 0


class CustomerDocumentInline(admin.TabularInline):
    model = CustomerDocument
    extra = 0


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'name', 'customer_class', 'status',
        'currency', 'credit_limit', 'credit_used', 'tenant',
    )
    list_filter = ('status', 'customer_class', 'currency', 'tenant')
    search_fields = ('code', 'name', 'legal_name', 'tax_id', 'email')
    inlines = [CustomerContactInline, CustomerDocumentInline]
    autocomplete_fields = ('category', 'default_price_list', 'default_warehouse')


@admin.register(CustomerContact)
class CustomerContactAdmin(admin.ModelAdmin):
    list_display = (
        'full_name', 'customer', 'role', 'email', 'phone_primary',
        'is_primary', 'is_active',
    )
    list_filter = ('role', 'is_primary', 'is_active', 'tenant')
    search_fields = ('full_name', 'email', 'phone_primary', 'customer__name')


@admin.register(CommunicationLog)
class CommunicationLogAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'customer', 'type', 'direction', 'subject',
        'occurred_at', 'status',
    )
    list_filter = ('type', 'direction', 'status', 'tenant')
    search_fields = ('code', 'subject', 'body', 'customer__name')
    date_hierarchy = 'occurred_at'
    readonly_fields = ('code', 'created_by', 'created_at', 'updated_at')


@admin.register(CustomerDocument)
class CustomerDocumentAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'customer', 'doc_type', 'expires_at', 'uploaded_by', 'created_at',
    )
    list_filter = ('doc_type', 'tenant')
    search_fields = ('title', 'customer__name')


# ----- 17.2 -----

class SalesOrderLineInline(admin.TabularInline):
    model = SalesOrderLine
    extra = 0
    autocomplete_fields = ('product',)
    readonly_fields = ('line_total', 'line_tax', 'line_discount')


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'customer', 'status', 'priority', 'credit_hold',
        'order_date', 'requested_delivery_date', 'grand_total', 'currency', 'tenant',
    )
    list_filter = ('status', 'priority', 'credit_hold', 'currency', 'tenant')
    search_fields = ('code', 'customer_po_number', 'customer__name')
    date_hierarchy = 'order_date'
    inlines = [SalesOrderLineInline]
    readonly_fields = (
        'code', 'subtotal', 'tax_total', 'discount_total', 'grand_total',
        'confirmed_at', 'cancelled_at',
    )


@admin.register(SalesOrderLine)
class SalesOrderLineAdmin(admin.ModelAdmin):
    list_display = (
        'sales_order', 'line_no', 'product', 'qty_ordered', 'unit_price',
        'line_total', 'is_make_to_order',
    )
    list_filter = ('is_make_to_order', 'tenant')
    search_fields = ('sales_order__code', 'product__name')


@admin.register(SalesOrderRevision)
class SalesOrderRevisionAdmin(admin.ModelAdmin):
    list_display = ('sales_order', 'version_no', 'revised_by', 'revised_at')
    list_filter = ('tenant',)
    search_fields = ('sales_order__code', 'reason')
    readonly_fields = ('snapshot_json',)


@admin.register(SalesOrderApprovalLog)
class SalesOrderApprovalLogAdmin(admin.ModelAdmin):
    list_display = (
        'sales_order', 'action', 'from_status', 'to_status',
        'performed_by', 'performed_at',
    )
    list_filter = ('action', 'tenant')
    search_fields = ('sales_order__code', 'notes')
    readonly_fields = ('performed_at',)


# ----- 17.3 -----

@admin.register(ATPCalculation)
class ATPCalculationAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'product', 'requested_qty', 'available_qty',
        'result_status', 'method', 'computed_at', 'tenant',
    )
    list_filter = ('result_status', 'method', 'tenant')
    search_fields = ('code', 'product__name')
    readonly_fields = ('code', 'snapshot_json', 'computed_at')


@admin.register(CTPCalculation)
class CTPCalculationAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'product', 'shortfall_qty', 'capable_qty',
        'earliest_completion_date', 'bottleneck_work_center', 'computed_at', 'tenant',
    )
    list_filter = ('tenant',)
    search_fields = ('code', 'product__name')
    readonly_fields = ('code', 'simulation_json', 'computed_at')


@admin.register(OrderPromise)
class OrderPromiseAdmin(admin.ModelAdmin):
    list_display = (
        'order_line', 'promise_type', 'promised_qty', 'promised_date',
        'confirmed_at', 'confirmed_by', 'tenant',
    )
    list_filter = ('promise_type', 'tenant')
    search_fields = ('order_line__sales_order__code',)


# ----- 17.4 -----

@admin.register(DeliveryRoute)
class DeliveryRouteAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'route_date', 'status', 'driver_name', 'vehicle_no', 'tenant')
    list_filter = ('status', 'tenant')
    search_fields = ('code', 'name', 'driver_name', 'vehicle_no')


class ShipmentLineInline(admin.TabularInline):
    model = ShipmentLine
    extra = 0
    autocomplete_fields = ('order_line', 'source_bin')


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'sales_order', 'status', 'carrier_name', 'tracking_number',
        'planned_ship_date', 'actual_delivery_date', 'tenant',
    )
    list_filter = ('status', 'tenant')
    search_fields = ('code', 'sales_order__code', 'tracking_number')
    inlines = [ShipmentLineInline]


@admin.register(ShipmentLine)
class ShipmentLineAdmin(admin.ModelAdmin):
    list_display = ('shipment', 'order_line', 'qty_to_ship', 'qty_shipped', 'pick_status', 'tenant')
    list_filter = ('pick_status', 'tenant')


@admin.register(ProofOfDelivery)
class ProofOfDeliveryAdmin(admin.ModelAdmin):
    list_display = ('code', 'shipment', 'received_by_name', 'delivered_at', 'tenant')
    list_filter = ('tenant',)
    search_fields = ('code', 'shipment__code', 'received_by_name')


class SalesInvoiceLineInline(admin.TabularInline):
    model = SalesInvoiceLine
    extra = 0
    readonly_fields = ('line_total', 'line_tax', 'line_discount')


@admin.register(SalesInvoice)
class SalesInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'sales_order', 'shipment', 'invoice_date', 'due_date',
        'status', 'grand_total', 'amount_paid', 'tenant',
    )
    list_filter = ('status', 'tenant')
    search_fields = ('code', 'sales_order__code')
    date_hierarchy = 'invoice_date'
    inlines = [SalesInvoiceLineInline]
    readonly_fields = ('code', 'subtotal', 'tax_total', 'discount_total', 'grand_total')


@admin.register(SalesInvoiceLine)
class SalesInvoiceLineAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'description', 'qty', 'unit_price', 'line_total', 'tenant')
    list_filter = ('tenant',)
