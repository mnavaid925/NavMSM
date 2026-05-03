"""Module 5 — Material Requirements Planning (MRP).

Sub-modules:
    5.1  Demand Forecasting                      (ForecastModel,
                                                  SeasonalityProfile,
                                                  ForecastRun, ForecastResult)
    5.2  Net Requirements Calculation            (InventorySnapshot,
                                                  ScheduledReceipt,
                                                  MRPCalculation, NetRequirement)
    5.3  Purchase Requisition Auto-Generation    (MRPPurchaseRequisition)
    5.4  MRP Exception Management                (MRPException)
    5.5  MRP Run & Simulation                    (MRPRun, MRPRunResult)

Reuses:
    apps.plm.models.Product               — part master
    apps.bom.models.BillOfMaterials       — multi-level explosion via .explode()
    apps.pps.models.MasterProductionSchedule  — optional source for end-item demand

Note on InventorySnapshot:
    Until Module 8 (Inventory & Warehouse) ships, this is the canonical store
    of on-hand qty / safety stock / reorder point / lead time per item. When
    Module 8 lands, the Inventory module is expected to populate these rows
    by aggregating bin-level stock — the MRP engine will not need to change.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.bom.models import BillOfMaterials
from apps.core.models import TenantAwareModel, TimeStampedModel
from apps.plm.models import Product
from apps.pps.models import MasterProductionSchedule


# ============================================================================
# 5.1  DEMAND FORECASTING
# ============================================================================

class ForecastModel(TenantAwareModel, TimeStampedModel):
    """Reusable forecast configuration — algorithm + parameters + horizon."""

    METHOD_CHOICES = [
        ('moving_avg', 'Moving Average'),
        ('weighted_ma', 'Weighted Moving Average'),
        ('simple_exp_smoothing', 'Simple Exponential Smoothing'),
        ('naive_seasonal', 'Naive Seasonal'),
    ]
    PERIOD_CHOICES = [
        ('day', 'Daily'),
        ('week', 'Weekly'),
        ('month', 'Monthly'),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    method = models.CharField(max_length=30, choices=METHOD_CHOICES, default='moving_avg')
    params = models.JSONField(
        default=dict, blank=True,
        help_text='Method parameters: {"window": 3} for moving_avg, '
                  '{"alpha": 0.3} for exp smoothing, '
                  '{"weights": [0.2,0.3,0.5]} for weighted_ma, '
                  '{"season_length": 12} for naive_seasonal.',
    )
    period_type = models.CharField(max_length=10, choices=PERIOD_CHOICES, default='week')
    horizon_periods = models.PositiveSmallIntegerField(
        default=12,
        validators=[MinValueValidator(1), MaxValueValidator(104)],
        help_text='How many periods ahead to forecast.',
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='forecast_models_created',
    )

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'name')
        verbose_name = 'Forecast Model'

    def __str__(self):
        return f'{self.name} ({self.get_method_display()})'


class SeasonalityProfile(TenantAwareModel, TimeStampedModel):
    """Per-product seasonal index for naive_seasonal forecasting."""

    PERIOD_CHOICES = [
        ('week', 'Weekly (1-52)'),
        ('month', 'Monthly (1-12)'),
    ]

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='seasonality_profiles',
    )
    period_type = models.CharField(max_length=10, choices=PERIOD_CHOICES, default='month')
    period_index = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(52)],
        help_text='1-12 for monthly, 1-52 for weekly.',
    )
    seasonal_index = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal('1.0000'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Multiplier vs. baseline. 1.0 = neutral, 1.2 = 20% above, 0.8 = 20% below.',
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['product', 'period_type', 'period_index']
        unique_together = ('tenant', 'product', 'period_type', 'period_index')
        verbose_name = 'Seasonality Profile'

    def __str__(self):
        return f'{self.product.sku} · {self.get_period_type_display()} #{self.period_index} · {self.seasonal_index}'


class ForecastRun(TenantAwareModel, TimeStampedModel):
    """Execution log of running a ForecastModel against historical data."""

    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    run_number = models.CharField(max_length=30)
    forecast_model = models.ForeignKey(
        ForecastModel, on_delete=models.PROTECT, related_name='runs',
    )
    run_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='forecast_runs_started',
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'run_number')
        verbose_name = 'Forecast Run'

    def __str__(self):
        return f'{self.run_number} — {self.forecast_model.name}'


class ForecastResult(TenantAwareModel, TimeStampedModel):
    """Single forecasted period output produced by a ForecastRun."""

    run = models.ForeignKey(
        ForecastRun, on_delete=models.CASCADE, related_name='results',
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='forecast_results',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    forecasted_qty = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    lower_bound = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    upper_bound = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    confidence_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('80'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )

    class Meta:
        ordering = ['run', 'product', 'period_start']
        unique_together = ('run', 'product', 'period_start')
        verbose_name = 'Forecast Result'

    def __str__(self):
        return f'{self.run.run_number} · {self.product.sku} · {self.period_start} · {self.forecasted_qty}'


# ============================================================================
# 5.2  NET REQUIREMENTS CALCULATION
# ============================================================================

class InventorySnapshot(TenantAwareModel, TimeStampedModel):
    """Per-product inventory state used as input to the MRP engine.

    Stand-in for the future Inventory module (Module 8). Will be replaced
    by aggregated bin-level data once that module ships — the MRP engine
    reads from this single row per (tenant, product) and is unaffected.
    """

    LOT_SIZE_CHOICES = [
        ('l4l', 'Lot-for-Lot'),
        ('foq', 'Fixed Order Quantity'),
        ('poq', 'Period Order Quantity'),
        ('min_max', 'Min-Max'),
    ]

    product = models.OneToOneField(
        Product, on_delete=models.CASCADE, related_name='inventory_snapshot',
    )
    on_hand_qty = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    safety_stock = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    reorder_point = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    lead_time_days = models.PositiveSmallIntegerField(
        default=7,
        validators=[MaxValueValidator(365)],
    )
    lot_size_method = models.CharField(
        max_length=10, choices=LOT_SIZE_CHOICES, default='l4l',
    )
    lot_size_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='FOQ size, POQ period count, or Min-Max minimum.',
    )
    lot_size_max = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Min-Max upper bound. Ignored for other methods.',
    )
    as_of_date = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['product__sku']
        verbose_name = 'Inventory Snapshot'

    def __str__(self):
        return f'{self.product.sku} · on-hand {self.on_hand_qty} · {self.get_lot_size_method_display()}'


class ScheduledReceipt(TenantAwareModel, TimeStampedModel):
    """Incoming supply pegged to a date — open POs, planned production, transfers."""

    RECEIPT_TYPE_CHOICES = [
        ('open_po', 'Open Purchase Order'),
        ('planned_production', 'Planned Production'),
        ('transfer', 'Stock Transfer'),
    ]

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='scheduled_receipts',
    )
    receipt_type = models.CharField(max_length=30, choices=RECEIPT_TYPE_CHOICES, default='open_po')
    quantity = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    expected_date = models.DateField()
    reference = models.CharField(
        max_length=120, blank=True,
        help_text='External reference (e.g. PO# or ProductionOrder#).',
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['expected_date', 'product__sku']
        indexes = [models.Index(fields=['tenant', 'product', 'expected_date'])]
        verbose_name = 'Scheduled Receipt'

    def __str__(self):
        return f'{self.product.sku} · +{self.quantity} on {self.expected_date}'


class MRPCalculation(TenantAwareModel, TimeStampedModel):
    """Header for one MRP calculation snapshot — bounds the horizon + status."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('committed', 'Committed'),
        ('discarded', 'Discarded'),
    ]
    BUCKET_CHOICES = [
        ('day', 'Daily'),
        ('week', 'Weekly'),
    ]

    mrp_number = models.CharField(max_length=30)
    name = models.CharField(max_length=255)
    horizon_start = models.DateField()
    horizon_end = models.DateField()
    time_bucket = models.CharField(max_length=10, choices=BUCKET_CHOICES, default='week')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    source_mps = models.ForeignKey(
        MasterProductionSchedule, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mrp_calculations',
        help_text='Optional — if linked, end-item demand is pulled from MPS lines.',
    )
    description = models.TextField(blank=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mrp_calcs_started',
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    committed_at = models.DateTimeField(null=True, blank=True)
    committed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mrp_calcs_committed',
    )

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'mrp_number')
        verbose_name = 'MRP Calculation'
        verbose_name_plural = 'MRP Calculations'

    def __str__(self):
        return f'{self.mrp_number} — {self.name}'

    def is_editable(self):
        return self.status in ('draft',)

    def can_commit(self):
        return self.status == 'completed'


class NetRequirement(TenantAwareModel, TimeStampedModel):
    """Gross-to-net result row produced by the MRP engine."""

    LOT_SIZE_CHOICES = InventorySnapshot.LOT_SIZE_CHOICES

    mrp_calculation = models.ForeignKey(
        MRPCalculation, on_delete=models.CASCADE, related_name='net_requirements',
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='net_requirements',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    bom_level = models.PositiveSmallIntegerField(
        default=0,
        help_text='0 = end item, 1 = first-level component, etc.',
    )
    parent_product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='dependent_requirements',
        help_text='Parent assembly that drove this dependent demand. Null for end items.',
    )
    gross_requirement = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    scheduled_receipts_qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    projected_on_hand = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    net_requirement = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    planned_order_qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    planned_release_date = models.DateField(null=True, blank=True)
    lot_size_method = models.CharField(max_length=10, choices=LOT_SIZE_CHOICES, default='l4l')
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['mrp_calculation', 'bom_level', 'period_start', 'product__sku']
        unique_together = ('mrp_calculation', 'product', 'period_start')
        indexes = [models.Index(fields=['tenant', 'mrp_calculation', 'product'])]
        verbose_name = 'Net Requirement'

    def __str__(self):
        return f'{self.product.sku} · {self.period_start} · net {self.net_requirement}'


# ============================================================================
# 5.3  PURCHASE REQUISITION AUTO-GENERATION
# ============================================================================

class MRPPurchaseRequisition(TenantAwareModel, TimeStampedModel):
    """MRP-suggested purchase requisition. Procurement (Module 9) will later
    convert approved rows into real PurchaseOrders via ``converted_reference``.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('converted', 'Converted'),
        ('cancelled', 'Cancelled'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('rush', 'Rush'),
    ]

    pr_number = models.CharField(max_length=30)
    mrp_calculation = models.ForeignKey(
        MRPCalculation, on_delete=models.CASCADE, related_name='purchase_requisitions',
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='mrp_purchase_requisitions',
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    required_by_date = models.DateField()
    suggested_release_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mrp_prs_approved',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    converted_reference = models.CharField(
        max_length=120, blank=True,
        help_text='Free-text reference to the converted PO (legacy / kept for back-compat).',
    )
    # Module 9 - Procurement bridge: direct FK to the converted PO when the
    # convert_pr_to_po service is invoked. additive + nullable.
    converted_po = models.ForeignKey(
        'procurement.PurchaseOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='source_requisitions',
    )

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'pr_number')
        verbose_name = 'MRP Purchase Requisition'
        verbose_name_plural = 'MRP Purchase Requisitions'

    def __str__(self):
        return f'{self.pr_number} · {self.product.sku} × {self.quantity}'

    def is_editable(self):
        return self.status == 'draft'

    def can_approve(self):
        return self.status == 'draft'

    def can_cancel(self):
        return self.status in ('draft', 'approved')


# ============================================================================
# 5.4  MRP EXCEPTION MANAGEMENT
# ============================================================================

class MRPException(TenantAwareModel, TimeStampedModel):
    """Action message produced by the MRP engine. Operators acknowledge,
    resolve, or ignore each row.
    """

    EXCEPTION_TYPE_CHOICES = [
        ('late_order', 'Late Order'),
        ('expedite', 'Expedite Required'),
        ('defer', 'Defer Possible'),
        ('cancel', 'Cancel Recommended'),
        ('release_early', 'Release Early'),
        ('below_min', 'Below Min Lot Size'),
        ('above_max', 'Above Max Lot Size'),
        ('no_routing', 'No Routing Available'),
        ('no_bom', 'No Released BOM'),
    ]
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    ACTION_CHOICES = [
        ('expedite', 'Expedite'),
        ('defer', 'Defer'),
        ('cancel', 'Cancel'),
        ('release_early', 'Release Early'),
        ('manual_review', 'Manual Review'),
        ('no_action', 'No Action Needed'),
    ]
    TARGET_TYPE_CHOICES = [
        ('production_order', 'Production Order'),
        ('purchase_requisition', 'Purchase Requisition'),
        ('mps_line', 'MPS Line'),
        ('none', 'None'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
        ('ignored', 'Ignored'),
    ]

    mrp_calculation = models.ForeignKey(
        MRPCalculation, on_delete=models.CASCADE, related_name='exceptions',
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='mrp_exceptions',
    )
    exception_type = models.CharField(max_length=30, choices=EXCEPTION_TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    message = models.TextField()
    recommended_action = models.CharField(
        max_length=20, choices=ACTION_CHOICES, default='manual_review',
    )
    target_type = models.CharField(max_length=30, choices=TARGET_TYPE_CHOICES, default='none')
    target_id = models.BigIntegerField(
        null=True, blank=True,
        help_text='ID of the row in the target_type table. No FK because targets '
                  'live in different apps and may move under refactors.',
    )
    current_date = models.DateField(null=True, blank=True)
    recommended_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mrp_exceptions_resolved',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-severity', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'mrp_calculation', 'status']),
            models.Index(fields=['tenant', 'severity', 'status']),
        ]
        verbose_name = 'MRP Exception'

    def __str__(self):
        return f'{self.get_exception_type_display()} · {self.product.sku} · {self.get_severity_display()}'


# ============================================================================
# 5.5  MRP RUN & SIMULATION
# ============================================================================

class MRPRun(TenantAwareModel, TimeStampedModel):
    """Top-level MRP execution log — wraps an MRPCalculation with run intent."""

    RUN_TYPE_CHOICES = [
        ('regenerative', 'Regenerative'),
        ('net_change', 'Net Change'),
        ('simulation', 'Simulation'),
    ]
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('applied', 'Applied'),
        ('discarded', 'Discarded'),
    ]

    run_number = models.CharField(max_length=30)
    name = models.CharField(max_length=255)
    run_type = models.CharField(max_length=20, choices=RUN_TYPE_CHOICES, default='regenerative')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    mrp_calculation = models.ForeignKey(
        MRPCalculation, on_delete=models.PROTECT, related_name='runs',
        help_text='The working calculation snapshot this run produced. PROTECT '
                  'so deleting a calculation that still has runs surfaces an '
                  'explicit error rather than silently destroying run history.',
    )
    source_mps = models.ForeignKey(
        MasterProductionSchedule, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mrp_runs',
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mrp_runs_started',
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mrp_runs_applied',
    )
    commit_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'run_number')
        verbose_name = 'MRP Run'

    def __str__(self):
        return f'{self.run_number} — {self.name} ({self.get_status_display()})'

    def can_start(self):
        return self.status == 'queued'

    def can_apply(self):
        return self.status == 'completed' and self.run_type != 'simulation'

    def can_discard(self):
        return self.status in ('completed', 'failed')


class MRPRunResult(TenantAwareModel, TimeStampedModel):
    """KPI summary captured after an MRPRun completes."""

    run = models.OneToOneField(
        MRPRun, on_delete=models.CASCADE, related_name='result',
    )
    total_planned_orders = models.PositiveIntegerField(default=0)
    total_pr_suggestions = models.PositiveIntegerField(default=0)
    total_exceptions = models.PositiveIntegerField(default=0)
    late_orders_count = models.PositiveIntegerField(default=0)
    coverage_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text='Percentage of demand covered by available supply + planned orders.',
    )
    summary_json = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-computed_at']
        verbose_name = 'MRP Run Result'

    def __str__(self):
        return f'{self.run.run_number} result · cov {self.coverage_pct}%'
