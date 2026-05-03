"""Module 8 — Inventory & Warehouse Management.

Sub-modules:
    8.1  Multi-Warehouse Inventory       (Warehouse, WarehouseZone, StorageBin, StockItem)
    8.2  Goods Receipt & Putaway         (GoodsReceiptNote, GRNLine, PutawayTask)
    8.3  Inventory Movements & Transfers (StockMovement, StockTransfer, StockTransferLine,
                                          StockAdjustment, StockAdjustmentLine)
    8.4  Cycle Counting & Physical Audit (CycleCountPlan, CycleCountSheet, CycleCountLine)
    8.5  Lot / Serial / Batch Tracking   (Lot, SerialNumber)

Cross-module integration:
    - apps.plm.Product.tracking_mode is the source of truth for whether a product is
      lot-tracked, serial-tracked, both, or neither.
    - apps.inventory.signals listens on apps.mes.ProductionReport to auto-emit
      StockMovement(production_in) rows for finished good qty.
    - apps.qms.IncomingInspection can be referenced from a GoodsReceiptNote so an
      accept decision flows into a receipt with one click.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel


# ============================================================================
# 8.1  MULTI-WAREHOUSE INVENTORY
# ============================================================================

class Warehouse(TenantAwareModel, TimeStampedModel):
    """Top-level physical or logical storage location."""

    code = models.CharField(max_length=20)
    name = models.CharField(max_length=120)
    address = models.TextField(blank=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='managed_warehouses',
    )
    is_default = models.BooleanField(
        default=False,
        help_text='Default warehouse for auto-generated movements (e.g. MES production_in).',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} — {self.name}'


class WarehouseZone(TenantAwareModel, TimeStampedModel):
    ZONE_TYPE_CHOICES = [
        ('receiving', 'Receiving'),
        ('storage', 'Storage'),
        ('picking', 'Picking'),
        ('shipping', 'Shipping'),
        ('quarantine', 'Quarantine'),
    ]

    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name='zones',
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=120)
    zone_type = models.CharField(max_length=20, choices=ZONE_TYPE_CHOICES, default='storage')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['warehouse', 'code']
        unique_together = ('warehouse', 'code')

    def __str__(self):
        return f'{self.warehouse.code}/{self.code}'


class StorageBin(TenantAwareModel, TimeStampedModel):
    BIN_TYPE_CHOICES = [
        ('shelf', 'Shelf'),
        ('pallet', 'Pallet'),
        ('rack', 'Rack'),
        ('floor', 'Floor'),
        ('bulk', 'Bulk'),
    ]

    zone = models.ForeignKey(WarehouseZone, on_delete=models.CASCADE, related_name='bins')
    code = models.CharField(max_length=30)
    bin_type = models.CharField(max_length=20, choices=BIN_TYPE_CHOICES, default='shelf')
    capacity = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Maximum units this bin can hold (0 = unlimited).',
    )
    abc_class = models.CharField(
        max_length=1,
        choices=[('A', 'A'), ('B', 'B'), ('C', 'C')],
        blank=True, default='',
        help_text='ABC velocity classification (set by cycle-count service).',
    )
    is_blocked = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['zone', 'code']
        unique_together = ('zone', 'code')

    def __str__(self):
        return f'{self.zone}/{self.code}'

    @property
    def warehouse(self):
        return self.zone.warehouse


class StockItem(TenantAwareModel, TimeStampedModel):
    """Per-bin per-product (per-lot, per-serial) inventory denorm.

    Auto-maintained by `apps.inventory.services.movements.post_movement()` —
    rows are created on first receipt and updated atomically on every movement.
    Use `qty_available` for picking decisions; do NOT mutate `qty_on_hand` directly.
    """

    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='stock_items',
    )
    bin = models.ForeignKey(StorageBin, on_delete=models.PROTECT, related_name='stock_items')
    lot = models.ForeignKey(
        'inventory.Lot', on_delete=models.PROTECT,
        null=True, blank=True, related_name='stock_items',
    )
    serial = models.ForeignKey(
        'inventory.SerialNumber', on_delete=models.PROTECT,
        null=True, blank=True, related_name='stock_items',
    )
    qty_on_hand = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    qty_reserved = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )

    class Meta:
        ordering = ['product', 'bin']
        unique_together = ('tenant', 'product', 'bin', 'lot', 'serial')

    def __str__(self):
        return f'{self.product.sku} @ {self.bin}: {self.qty_on_hand}'

    @property
    def qty_available(self):
        return self.qty_on_hand - self.qty_reserved


# ============================================================================
# 8.5  LOT / SERIAL / BATCH TRACKING
# ============================================================================
#
# Defined before GRN/movements so the FK targets exist for the schema migration.

class Lot(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('quarantine', 'Quarantine'),
        ('expired', 'Expired'),
        ('consumed', 'Consumed'),
    ]

    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='lots',
    )
    lot_number = models.CharField(max_length=60)
    manufactured_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    supplier_name = models.CharField(max_length=255, blank=True)
    coa_reference = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-manufactured_date', 'lot_number']
        unique_together = ('tenant', 'product', 'lot_number')

    def __str__(self):
        return f'{self.product.sku}/{self.lot_number}'

    @property
    def is_expiring_soon(self):
        if not self.expiry_date:
            return False
        return (self.expiry_date - timezone.now().date()).days <= 30


class SerialNumber(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('reserved', 'Reserved'),
        ('shipped', 'Shipped'),
        ('scrapped', 'Scrapped'),
    ]

    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='serial_numbers',
    )
    serial_number = models.CharField(max_length=60)
    lot = models.ForeignKey(
        Lot, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='serial_numbers',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['serial_number']
        unique_together = ('tenant', 'product', 'serial_number')

    def __str__(self):
        return f'{self.product.sku}/{self.serial_number}'


# ============================================================================
# 8.2  GOODS RECEIPT & PUTAWAY
# ============================================================================

class GoodsReceiptNote(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('received', 'Received'),
        ('putaway_pending', 'Putaway Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    grn_number = models.CharField(max_length=20)
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name='grns',
    )
    supplier_name = models.CharField(
        max_length=255, blank=True,
        help_text='Free-text supplier (Module 9 / Procurement will replace with FK).',
    )
    po_reference = models.CharField(max_length=60, blank=True)
    incoming_inspection = models.ForeignKey(
        'qms.IncomingInspection', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='goods_receipts',
    )
    received_date = models.DateField(default=timezone.now)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='received_grns',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-received_date', '-id']
        unique_together = ('tenant', 'grn_number')

    def __str__(self):
        return self.grn_number

    def save(self, *args, **kwargs):
        if not self.grn_number and self.tenant_id:
            last = (
                GoodsReceiptNote.all_objects
                .filter(tenant=self.tenant)
                .order_by('-id')
                .first()
            )
            seq = (last.id + 1) if last else 1
            self.grn_number = f'GRN-{seq:05d}'
        super().save(*args, **kwargs)


class GRNLine(TenantAwareModel, TimeStampedModel):
    grn = models.ForeignKey(
        GoodsReceiptNote, on_delete=models.CASCADE, related_name='lines',
    )
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='grn_lines',
    )
    expected_qty = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    received_qty = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    lot_number = models.CharField(max_length=60, blank=True)
    serial_numbers = models.TextField(
        blank=True,
        help_text='Comma-separated serial numbers for serial-tracked products.',
    )
    receiving_zone = models.ForeignKey(
        WarehouseZone, on_delete=models.PROTECT, related_name='grn_lines',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['grn', 'id']

    def __str__(self):
        return f'{self.grn.grn_number} :: {self.product.sku}'


class PutawayTask(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    STRATEGY_CHOICES = [
        ('fixed_bin', 'Fixed Bin'),
        ('nearest_empty', 'Nearest Empty'),
        ('abc_zone', 'ABC Zone'),
        ('directed', 'Directed'),
    ]

    grn_line = models.ForeignKey(
        GRNLine, on_delete=models.CASCADE, related_name='putaway_tasks',
    )
    suggested_bin = models.ForeignKey(
        StorageBin, on_delete=models.PROTECT,
        null=True, blank=True, related_name='putaway_suggestions',
    )
    actual_bin = models.ForeignKey(
        StorageBin, on_delete=models.PROTECT,
        null=True, blank=True, related_name='putaway_actuals',
    )
    qty = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES, default='nearest_empty')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='completed_putaways',
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f'Putaway #{self.id} ({self.status})'


# ============================================================================
# 8.3  INVENTORY MOVEMENTS & TRANSFERS
# ============================================================================

class StockMovement(TenantAwareModel, TimeStampedModel):
    """Append-only stock ledger. Source of truth for all inventory changes."""

    MOVEMENT_TYPE_CHOICES = [
        ('receipt', 'Receipt'),
        ('issue', 'Issue'),
        ('transfer', 'Transfer'),
        ('adjustment', 'Adjustment'),
        ('production_in', 'Production In'),
        ('production_out', 'Production Out'),
        ('scrap', 'Scrap'),
        ('cycle_count', 'Cycle Count Variance'),
    ]

    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPE_CHOICES)
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='stock_movements',
    )
    from_bin = models.ForeignKey(
        StorageBin, on_delete=models.PROTECT,
        null=True, blank=True, related_name='outgoing_movements',
    )
    to_bin = models.ForeignKey(
        StorageBin, on_delete=models.PROTECT,
        null=True, blank=True, related_name='incoming_movements',
    )
    qty = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    lot = models.ForeignKey(
        Lot, on_delete=models.PROTECT,
        null=True, blank=True, related_name='movements',
    )
    serial = models.ForeignKey(
        SerialNumber, on_delete=models.PROTECT,
        null=True, blank=True, related_name='movements',
    )
    reason = models.CharField(max_length=120, blank=True)
    reference = models.CharField(max_length=120, blank=True)
    production_report = models.ForeignKey(
        'mes.ProductionReport', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='stock_movements',
    )
    incoming_inspection = models.ForeignKey(
        'qms.IncomingInspection', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='stock_movements',
    )
    grn_line = models.ForeignKey(
        GRNLine, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='stock_movements',
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='posted_movements',
    )
    posted_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-posted_at', '-id']
        indexes = [
            models.Index(fields=['tenant', 'product', '-posted_at']),
            models.Index(fields=['tenant', 'movement_type', '-posted_at']),
        ]

    def __str__(self):
        return f'{self.get_movement_type_display()} {self.product.sku} x{self.qty}'


class StockTransfer(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_transit', 'In Transit'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]

    transfer_number = models.CharField(max_length=20)
    source_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name='outgoing_transfers',
    )
    destination_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name='incoming_transfers',
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='requested_transfers',
    )
    requested_date = models.DateField(default=timezone.now)
    expected_arrival = models.DateField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='received_transfers',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-requested_date', '-id']
        unique_together = ('tenant', 'transfer_number')

    def __str__(self):
        return self.transfer_number

    def save(self, *args, **kwargs):
        if not self.transfer_number and self.tenant_id:
            last = (
                StockTransfer.all_objects
                .filter(tenant=self.tenant).order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.transfer_number = f'TRF-{seq:05d}'
        super().save(*args, **kwargs)


class StockTransferLine(TenantAwareModel, TimeStampedModel):
    transfer = models.ForeignKey(
        StockTransfer, on_delete=models.CASCADE, related_name='lines',
    )
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='transfer_lines',
    )
    qty = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    source_bin = models.ForeignKey(
        StorageBin, on_delete=models.PROTECT, related_name='transfer_source_lines',
    )
    destination_bin = models.ForeignKey(
        StorageBin, on_delete=models.PROTECT,
        null=True, blank=True, related_name='transfer_dest_lines',
    )
    lot = models.ForeignKey(
        Lot, on_delete=models.PROTECT,
        null=True, blank=True, related_name='transfer_lines',
    )
    serial = models.ForeignKey(
        SerialNumber, on_delete=models.PROTECT,
        null=True, blank=True, related_name='transfer_lines',
    )

    class Meta:
        ordering = ['transfer', 'id']

    def __str__(self):
        return f'{self.transfer.transfer_number} :: {self.product.sku}'


class StockAdjustment(TenantAwareModel, TimeStampedModel):
    REASON_CHOICES = [
        ('damage', 'Damage'),
        ('loss', 'Loss / Theft'),
        ('found', 'Found'),
        ('count_correction', 'Count Correction'),
        ('expiry', 'Expiry'),
        ('quality_hold', 'Quality Hold'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled'),
    ]

    adjustment_number = models.CharField(max_length=20)
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name='adjustments',
    )
    reason = models.CharField(max_length=30, choices=REASON_CHOICES, default='other')
    reason_notes = models.TextField()
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='posted_adjustments',
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    class Meta:
        ordering = ['-id']
        unique_together = ('tenant', 'adjustment_number')

    def __str__(self):
        return self.adjustment_number

    def save(self, *args, **kwargs):
        if not self.adjustment_number and self.tenant_id:
            last = (
                StockAdjustment.all_objects
                .filter(tenant=self.tenant).order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.adjustment_number = f'ADJ-{seq:05d}'
        super().save(*args, **kwargs)


class StockAdjustmentLine(TenantAwareModel, TimeStampedModel):
    adjustment = models.ForeignKey(
        StockAdjustment, on_delete=models.CASCADE, related_name='lines',
    )
    bin = models.ForeignKey(
        StorageBin, on_delete=models.PROTECT, related_name='adjustment_lines',
    )
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='adjustment_lines',
    )
    lot = models.ForeignKey(
        Lot, on_delete=models.PROTECT,
        null=True, blank=True, related_name='adjustment_lines',
    )
    serial = models.ForeignKey(
        SerialNumber, on_delete=models.PROTECT,
        null=True, blank=True, related_name='adjustment_lines',
    )
    system_qty = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0'))],
    )
    actual_qty = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0'))],
    )

    class Meta:
        ordering = ['adjustment', 'id']

    def __str__(self):
        return f'{self.adjustment.adjustment_number} :: {self.product.sku}'

    @property
    def variance(self):
        return self.actual_qty - self.system_qty


# ============================================================================
# 8.4  CYCLE COUNTING & PHYSICAL AUDIT
# ============================================================================

class CycleCountPlan(TenantAwareModel, TimeStampedModel):
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]

    name = models.CharField(max_length=120)
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name='cycle_count_plans',
    )
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='monthly')
    abc_class_filter = models.CharField(
        max_length=1, blank=True,
        choices=[('', 'All Classes'), ('A', 'A'), ('B', 'B'), ('C', 'C')],
        default='',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'name')

    def __str__(self):
        return self.name


class CycleCountSheet(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('counting', 'Counting'),
        ('reconciled', 'Reconciled'),
        ('cancelled', 'Cancelled'),
    ]

    sheet_number = models.CharField(max_length=20)
    plan = models.ForeignKey(
        CycleCountPlan, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sheets',
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name='cycle_count_sheets',
    )
    counted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='counted_sheets',
    )
    count_date = models.DateField(default=timezone.now)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reconciled_sheets',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-count_date', '-id']
        unique_together = ('tenant', 'sheet_number')

    def __str__(self):
        return self.sheet_number

    def save(self, *args, **kwargs):
        if not self.sheet_number and self.tenant_id:
            last = (
                CycleCountSheet.all_objects
                .filter(tenant=self.tenant).order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.sheet_number = f'CC-{seq:05d}'
        super().save(*args, **kwargs)


class CycleCountLine(TenantAwareModel, TimeStampedModel):
    sheet = models.ForeignKey(
        CycleCountSheet, on_delete=models.CASCADE, related_name='lines',
    )
    bin = models.ForeignKey(
        StorageBin, on_delete=models.PROTECT, related_name='cycle_count_lines',
    )
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='cycle_count_lines',
    )
    lot = models.ForeignKey(
        Lot, on_delete=models.PROTECT,
        null=True, blank=True, related_name='cycle_count_lines',
    )
    serial = models.ForeignKey(
        SerialNumber, on_delete=models.PROTECT,
        null=True, blank=True, related_name='cycle_count_lines',
    )
    system_qty = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    counted_qty = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0'))],
    )
    recount_required = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['sheet', 'id']

    def __str__(self):
        return f'{self.sheet.sheet_number} :: {self.product.sku} @ {self.bin}'

    @property
    def variance(self):
        if self.counted_qty is None:
            return None
        return self.counted_qty - self.system_qty
