"""Django admin registration for Module 17 - Sales."""
from django.contrib import admin

from .models import (
    CommunicationLog,
    Customer,
    CustomerCategory,
    CustomerContact,
    CustomerDocument,
    PriceList,
    PriceListItem,
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
    search_fields = ('price_list__name', 'product__name', 'product__code')
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
