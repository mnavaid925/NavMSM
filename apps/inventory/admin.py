"""Django admin for Module 8 — Inventory & Warehouse Management."""
from django.contrib import admin

from . import models


@admin.register(models.Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'tenant', 'is_default', 'is_active', 'manager')
    list_filter = ('is_default', 'is_active', 'tenant')
    search_fields = ('code', 'name')


@admin.register(models.WarehouseZone)
class WarehouseZoneAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'warehouse', 'zone_type', 'is_active')
    list_filter = ('zone_type', 'is_active', 'warehouse')
    search_fields = ('code', 'name')


@admin.register(models.StorageBin)
class StorageBinAdmin(admin.ModelAdmin):
    list_display = ('code', 'zone', 'bin_type', 'capacity', 'abc_class', 'is_blocked')
    list_filter = ('bin_type', 'abc_class', 'is_blocked', 'zone__warehouse')
    search_fields = ('code',)


@admin.register(models.StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'bin', 'lot', 'serial', 'qty_on_hand', 'qty_reserved')
    list_filter = ('bin__zone__warehouse',)
    search_fields = ('product__sku',)
    readonly_fields = ('qty_on_hand', 'qty_reserved')


@admin.register(models.Lot)
class LotAdmin(admin.ModelAdmin):
    list_display = ('lot_number', 'product', 'manufactured_date', 'expiry_date', 'status')
    list_filter = ('status',)
    search_fields = ('lot_number', 'product__sku')
    date_hierarchy = 'manufactured_date'


@admin.register(models.SerialNumber)
class SerialNumberAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'product', 'lot', 'status')
    list_filter = ('status',)
    search_fields = ('serial_number', 'product__sku')


class GRNLineInline(admin.TabularInline):
    model = models.GRNLine
    extra = 0
    raw_id_fields = ('product', 'receiving_zone')


@admin.register(models.GoodsReceiptNote)
class GoodsReceiptNoteAdmin(admin.ModelAdmin):
    list_display = ('grn_number', 'warehouse', 'supplier_name', 'received_date', 'status')
    list_filter = ('status', 'warehouse')
    search_fields = ('grn_number', 'supplier_name', 'po_reference')
    inlines = [GRNLineInline]


@admin.register(models.PutawayTask)
class PutawayTaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'grn_line', 'suggested_bin', 'actual_bin', 'qty', 'strategy', 'status')
    list_filter = ('status', 'strategy')


@admin.register(models.StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('id', 'movement_type', 'product', 'qty', 'from_bin', 'to_bin', 'posted_at')
    list_filter = ('movement_type',)
    search_fields = ('product__sku', 'reference')
    date_hierarchy = 'posted_at'

    def has_change_permission(self, request, obj=None):
        # Movements are append-only
        if obj is not None:
            return False
        return super().has_change_permission(request, obj)


class StockTransferLineInline(admin.TabularInline):
    model = models.StockTransferLine
    extra = 0
    raw_id_fields = ('product', 'source_bin', 'destination_bin', 'lot', 'serial')


@admin.register(models.StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ('transfer_number', 'source_warehouse', 'destination_warehouse', 'status', 'requested_date')
    list_filter = ('status',)
    search_fields = ('transfer_number',)
    inlines = [StockTransferLineInline]


class StockAdjustmentLineInline(admin.TabularInline):
    model = models.StockAdjustmentLine
    extra = 0
    raw_id_fields = ('bin', 'product', 'lot', 'serial')


@admin.register(models.StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('adjustment_number', 'warehouse', 'reason', 'status', 'posted_at')
    list_filter = ('reason', 'status')
    search_fields = ('adjustment_number',)
    inlines = [StockAdjustmentLineInline]


@admin.register(models.CycleCountPlan)
class CycleCountPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'warehouse', 'frequency', 'abc_class_filter', 'is_active')
    list_filter = ('frequency', 'is_active')
    search_fields = ('name',)


class CycleCountLineInline(admin.TabularInline):
    model = models.CycleCountLine
    extra = 0
    raw_id_fields = ('bin', 'product', 'lot', 'serial')


@admin.register(models.CycleCountSheet)
class CycleCountSheetAdmin(admin.ModelAdmin):
    list_display = ('sheet_number', 'warehouse', 'count_date', 'status', 'reconciled_at')
    list_filter = ('status', 'warehouse')
    search_fields = ('sheet_number',)
    inlines = [CycleCountLineInline]
