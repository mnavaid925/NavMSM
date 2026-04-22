from django.contrib import admin
from .models import (
    BillingAddress, BrandingSettings, EmailTemplate, HealthAlert, Invoice,
    InvoiceLineItem, Payment, Plan, Subscription, TenantAuditLog,
    TenantHealthSnapshot, UsageMeter,
)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'price_monthly', 'price_yearly', 'is_active', 'sort_order')
    list_filter = ('is_active', 'is_featured')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'plan', 'status', 'interval', 'current_period_end', 'cancel_at_period_end')
    list_filter = ('status', 'interval', 'plan')


class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('number', 'tenant', 'status', 'total', 'issue_date', 'due_date')
    list_filter = ('status',)
    search_fields = ('number',)
    inlines = [InvoiceLineItemInline]


admin.site.register(Payment)
admin.site.register(BillingAddress)
admin.site.register(UsageMeter)
admin.site.register(BrandingSettings)
admin.site.register(EmailTemplate)
admin.site.register(TenantAuditLog)
admin.site.register(TenantHealthSnapshot)
admin.site.register(HealthAlert)
