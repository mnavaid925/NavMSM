"""Module 12 - Cost Management & Accounting.

Sub-modules:
    12.1  Standard Costing                  (StandardCostVersion, StandardCost,
                                             StandardCostHistory)
    12.2  Actual Cost & Variance            (ActualCost, CostVariance)
    12.3  Work in Process (WIP) Accounting  (JobCost, WIPEntry)
    12.4  Overhead Allocation               (CostDriver, OverheadPool,
                                             OverheadRate, OverheadActualPool,
                                             DriverActuals, OverheadAllocation)
    12.5  Manufacturing Financial Reports   (AccountingPeriod, COGMReport,
                                             GrossMarginReport, PlantPnLReport)

Cross-module integration (additive, no schema changes to other apps except
plm.Product.standard_sale_price for revenue placeholder):
    - apps.labor.LaborBooking.post_save (kind=direct)   -> WIPEntry(labor_applied)
    - apps.labor.LaborBooking.post_save (kind=indirect) -> OverheadActualPool accum
    - apps.mes.ProductionReport.post_save (good_qty>0)  -> WIPEntry(completion)

Lessons applied:
    * L-01 unique_together with tenant excluded -> form-level clean()
    * L-02 every Decimal carries explicit MinValueValidator
    * L-03 view+template status gate parity via is_*() helpers
    * L-12 auto-numbering retry loop in views (mirrors labor pattern)
    * L-13 transaction.atomic() around denorm bumps
    * L-14 per-workflow forms enforce required fields
    * L-17 PROTECT on audit-trail children (WIPEntry -> JobCost)
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel


# Common decimal validator: accepts negatives (variances, reversals)
NEG_BOUND = Decimal('-99999999.9999')
NON_NEG = MinValueValidator(Decimal('0'))
SIGNED = MinValueValidator(NEG_BOUND)


# ============================================================================
# 12.1  STANDARD COSTING
# ============================================================================

class StandardCostVersion(TenantAwareModel, TimeStampedModel):
    """Effective-dated container for a frozen set of standard costs.

    Workflow: draft -> approved -> active -> archived.
    Activating a version auto-archives any prior overlapping ``active`` rows.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]

    version_number = models.CharField(max_length=15)
    name = models.CharField(max_length=120)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_cost_versions',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_cost_versions',
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-effective_from', 'version_number']
        unique_together = ('tenant', 'version_number')

    def __str__(self):
        return f'{self.version_number} - {self.name}'

    def is_editable(self) -> bool:
        return self.status == 'draft'

    def is_approvable(self) -> bool:
        return self.status == 'draft'

    def is_activatable(self) -> bool:
        return self.status == 'approved'

    def is_archivable(self) -> bool:
        return self.status == 'active'

    def save(self, *args, **kwargs):
        if not self.version_number and self.tenant_id:
            last = (
                StandardCostVersion.all_objects
                .filter(tenant_id=self.tenant_id, version_number__startswith='SCV-')
                .order_by('-version_number').first()
            )
            n = 1
            if last and last.version_number.startswith('SCV-'):
                try:
                    n = int(last.version_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.version_number = f'SCV-{n:05d}'
        super().save(*args, **kwargs)


class StandardCost(TenantAwareModel, TimeStampedModel):
    """Per-product frozen standard cost inside a version."""

    SOURCE_CHOICES = [
        ('bom_rollup', 'BOM Cost Rollup'),
        ('manual', 'Manual'),
        ('imported', 'Imported'),
    ]

    version = models.ForeignKey(
        StandardCostVersion, on_delete=models.CASCADE, related_name='costs',
    )
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='standard_costs',
    )
    material_cost = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    labor_cost = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    overhead_cost = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    tooling_cost = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    subassembly_cost = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    total_cost = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    source = models.CharField(max_length=12, choices=SOURCE_CHOICES, default='manual')
    currency = models.CharField(max_length=3, default='USD')

    class Meta:
        ordering = ['version', 'product__sku']
        unique_together = ('version', 'product')

    def __str__(self):
        return f'{self.version.version_number} | {self.product.sku} | {self.total_cost}'

    def save(self, *args, **kwargs):
        self.total_cost = (
            (self.material_cost or Decimal('0'))
            + (self.labor_cost or Decimal('0'))
            + (self.overhead_cost or Decimal('0'))
            + (self.tooling_cost or Decimal('0'))
            + (self.subassembly_cost or Decimal('0'))
        )
        super().save(*args, **kwargs)


class StandardCostHistory(TenantAwareModel, TimeStampedModel):
    """Immutable revision log for changes to a StandardCost row."""

    cost = models.ForeignKey(
        StandardCost, on_delete=models.CASCADE, related_name='history',
    )
    field = models.CharField(max_length=40)
    old_value = models.CharField(max_length=64, blank=True)
    new_value = models.CharField(max_length=64, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='cost_history_changes',
    )
    changed_at = models.DateTimeField(default=timezone.now)
    change_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f'{self.cost} {self.field}: {self.old_value} -> {self.new_value}'


# ============================================================================
# 12.4  OVERHEAD ALLOCATION  (declared early — referenced by 12.3 / 12.5)
# ============================================================================

class CostDriver(TenantAwareModel, TimeStampedModel):
    """Tenant-level activity-driver catalog (machine_hours, units, sq_ft, kwh, etc.)."""

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30)
    unit_of_measure = models.CharField(max_length=30, default='hours')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class OverheadPool(TenantAwareModel, TimeStampedModel):
    """Pool of indirect costs (Factory Rent, Utilities, Supervision, ...)."""

    POOL_TYPE_CHOICES = [
        ('fixed', 'Fixed'),
        ('variable', 'Variable'),
        ('semi_variable', 'Semi-Variable'),
    ]
    ALLOCATION_METHOD_CHOICES = [
        ('abc', 'Activity-Based Costing'),
        ('volume', 'Volume-Based'),
        ('direct_labor_hours', 'Direct Labor Hours'),
        ('direct_labor_cost', 'Direct Labor Cost'),
        ('machine_hours', 'Machine Hours'),
    ]

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30)
    pool_type = models.CharField(max_length=15, choices=POOL_TYPE_CHOICES, default='fixed')
    default_driver = models.ForeignKey(
        CostDriver, on_delete=models.PROTECT, related_name='pools',
    )
    allocation_method = models.CharField(
        max_length=20, choices=ALLOCATION_METHOD_CHOICES, default='abc',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class AccountingPeriod(TenantAwareModel, TimeStampedModel):
    """Monthly (or quarterly) accounting period.

    Workflow: open -> locked -> closed. Locking refuses new WIPEntry posts.
    Closing is irreversible and finalizes the report set for the period.
    """

    PERIOD_TYPE_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('locked', 'Locked'),
        ('closed', 'Closed'),
    ]

    period_number = models.CharField(max_length=15)
    name = models.CharField(max_length=80)
    period_type = models.CharField(max_length=10, choices=PERIOD_TYPE_CHOICES, default='monthly')
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default='open')
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='locked_periods',
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='closed_periods',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_date']
        unique_together = ('tenant', 'start_date', 'end_date')

    def __str__(self):
        return f'{self.period_number} - {self.name}'

    def is_open(self) -> bool:
        return self.status == 'open'

    def is_lockable(self) -> bool:
        return self.status == 'open'

    def is_closable(self) -> bool:
        return self.status == 'locked'

    def save(self, *args, **kwargs):
        if not self.period_number and self.tenant_id:
            last = (
                AccountingPeriod.all_objects
                .filter(tenant_id=self.tenant_id, period_number__startswith='ACP-')
                .order_by('-period_number').first()
            )
            n = 1
            if last and last.period_number.startswith('ACP-'):
                try:
                    n = int(last.period_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.period_number = f'ACP-{n:05d}'
        super().save(*args, **kwargs)


class OverheadRate(TenantAwareModel, TimeStampedModel):
    """Period-scoped budgeted rate per pool.

    rate_per_driver_unit = budgeted_amount / budgeted_driver_qty (computed on save).
    """

    pool = models.ForeignKey(
        OverheadPool, on_delete=models.PROTECT, related_name='rates',
    )
    period = models.ForeignKey(
        AccountingPeriod, on_delete=models.PROTECT, related_name='overhead_rates',
    )
    driver = models.ForeignKey(
        CostDriver, on_delete=models.PROTECT, related_name='overhead_rates',
    )
    budgeted_amount = models.DecimalField(
        max_digits=16, decimal_places=2, validators=[NON_NEG],
    )
    budgeted_driver_qty = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    rate_per_driver_unit = models.DecimalField(
        max_digits=16, decimal_places=6, default=Decimal('0'), validators=[NON_NEG],
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['period', 'pool']
        unique_together = ('pool', 'period')

    def __str__(self):
        return f'{self.pool.code} | {self.period.name} | {self.rate_per_driver_unit}/u'

    def save(self, *args, **kwargs):
        if self.budgeted_driver_qty and self.budgeted_driver_qty > 0:
            self.rate_per_driver_unit = (
                self.budgeted_amount / self.budgeted_driver_qty
            ).quantize(Decimal('0.000001'))
        super().save(*args, **kwargs)


class OverheadActualPool(TenantAwareModel, TimeStampedModel):
    """Per-period rollup of actual indirect spend per pool.

    Fed by labor.LaborBooking(kind='indirect') accumulation + manual entries.
    """

    pool = models.ForeignKey(
        OverheadPool, on_delete=models.PROTECT, related_name='actual_pools',
    )
    period = models.ForeignKey(
        AccountingPeriod, on_delete=models.PROTECT, related_name='overhead_actuals',
    )
    actual_amount = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    last_updated_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['period', 'pool']
        unique_together = ('pool', 'period')

    def __str__(self):
        return f'{self.pool.code} | {self.period.name} | actual={self.actual_amount}'


class DriverActuals(TenantAwareModel, TimeStampedModel):
    """Recorded driver consumption per period per cost-center / production-order.

    XOR: exactly one of (cost_center, production_order) must be set.
    """

    driver = models.ForeignKey(
        CostDriver, on_delete=models.PROTECT, related_name='actuals',
    )
    period = models.ForeignKey(
        AccountingPeriod, on_delete=models.PROTECT, related_name='driver_actuals',
    )
    cost_center = models.ForeignKey(
        'labor.CostCenter', on_delete=models.PROTECT,
        null=True, blank=True, related_name='driver_actuals',
    )
    production_order = models.ForeignKey(
        'pps.ProductionOrder', on_delete=models.PROTECT,
        null=True, blank=True, related_name='driver_actuals',
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=4, validators=[NON_NEG],
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='recorded_driver_actuals',
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['tenant', 'driver', 'period']),
        ]

    def __str__(self):
        target = self.production_order or self.cost_center
        return f'{self.driver.code} | {self.period.name} | {target} | {self.quantity}'


class OverheadAllocation(TenantAwareModel, TimeStampedModel):
    """Materialized per-period allocation: pool x target x applied amount.

    Auto-numbered ``OHA-00001``. Idempotent natural key on
    (pool, period, target_cost_center, target_production_order).
    """

    allocation_number = models.CharField(max_length=15)
    pool = models.ForeignKey(
        OverheadPool, on_delete=models.PROTECT, related_name='allocations',
    )
    period = models.ForeignKey(
        AccountingPeriod, on_delete=models.PROTECT, related_name='overhead_allocations',
    )
    target_cost_center = models.ForeignKey(
        'labor.CostCenter', on_delete=models.PROTECT,
        null=True, blank=True, related_name='overhead_allocations',
    )
    target_production_order = models.ForeignKey(
        'pps.ProductionOrder', on_delete=models.PROTECT,
        null=True, blank=True, related_name='overhead_allocations',
    )
    driver_qty = models.DecimalField(
        max_digits=14, decimal_places=4, validators=[NON_NEG],
    )
    rate_applied = models.DecimalField(
        max_digits=16, decimal_places=6, validators=[NON_NEG],
    )
    applied_amount = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    posted_at = models.DateTimeField(default=timezone.now)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='posted_allocations',
    )
    is_reversed = models.BooleanField(default=False)
    reversal_reason = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-posted_at']
        unique_together = ('tenant', 'allocation_number')
        indexes = [
            models.Index(fields=['tenant', 'pool', 'period']),
            models.Index(fields=['tenant', 'target_production_order']),
            models.Index(fields=['tenant', 'target_cost_center']),
        ]

    def __str__(self):
        target = self.target_production_order or self.target_cost_center or 'unallocated'
        return f'{self.allocation_number} | {self.pool.code} | {target} | {self.applied_amount}'

    def save(self, *args, **kwargs):
        if not self.allocation_number and self.tenant_id:
            last = (
                OverheadAllocation.all_objects
                .filter(tenant_id=self.tenant_id, allocation_number__startswith='OHA-')
                .order_by('-allocation_number').first()
            )
            n = 1
            if last and last.allocation_number.startswith('OHA-'):
                try:
                    n = int(last.allocation_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.allocation_number = f'OHA-{n:05d}'
        if self.driver_qty is not None and self.rate_applied is not None:
            self.applied_amount = (
                self.driver_qty * self.rate_applied
            ).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)


# ============================================================================
# 12.3  WORK IN PROCESS (WIP) ACCOUNTING
# ============================================================================

class JobCost(TenantAwareModel, TimeStampedModel):
    """One per pps.ProductionOrder — the 'job' in job costing.

    Denorms total_material / total_labor / total_overhead / total_completion_credit
    plus wip_balance are bumped atomically by WIPEntry.save() / pre_delete.
    """

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
    ]

    job_number = models.CharField(max_length=15)
    production_order = models.OneToOneField(
        'pps.ProductionOrder', on_delete=models.PROTECT, related_name='job_cost',
    )
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default='open')
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='closed_jobs',
    )
    total_material = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    total_labor = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    total_overhead = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    total_completion_credit = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    wip_balance = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-opened_at']
        unique_together = ('tenant', 'job_number')
        indexes = [
            models.Index(fields=['tenant', 'status']),
        ]

    def __str__(self):
        return f'{self.job_number} | {self.production_order} | {self.status}'

    def is_closable(self) -> bool:
        return self.status == 'open'

    def recompute_balance(self):
        self.wip_balance = (
            (self.total_material or Decimal('0'))
            + (self.total_labor or Decimal('0'))
            + (self.total_overhead or Decimal('0'))
            - (self.total_completion_credit or Decimal('0'))
        )

    def save(self, *args, **kwargs):
        if not self.job_number and self.tenant_id:
            last = (
                JobCost.all_objects
                .filter(tenant_id=self.tenant_id, job_number__startswith='JC-')
                .order_by('-job_number').first()
            )
            n = 1
            if last and last.job_number.startswith('JC-'):
                try:
                    n = int(last.job_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.job_number = f'JC-{n:05d}'
        self.recompute_balance()
        super().save(*args, **kwargs)


class WIPEntry(TenantAwareModel, TimeStampedModel):
    """Append-only per-job WIP ledger.

    entry_type drives which JobCost denorm gets bumped on save(); pre_delete
    reverses. Idempotency on cross-module hooks is enforced by the four
    unique_together constraints below.
    """

    ENTRY_TYPE_CHOICES = [
        ('material_issued', 'Material Issued'),
        ('labor_applied', 'Labor Applied'),
        ('overhead_applied', 'Overhead Applied'),
        ('completion', 'Completion'),
        ('variance', 'Variance'),
        ('adjustment', 'Adjustment'),
    ]

    entry_number = models.CharField(max_length=15)
    job = models.ForeignKey(
        JobCost, on_delete=models.PROTECT, related_name='wip_entries',
    )
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPE_CHOICES)
    amount = models.DecimalField(
        max_digits=16, decimal_places=2, validators=[SIGNED],
        help_text='Signed: completion / reversal entries are negative.',
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'), validators=[SIGNED],
    )
    unit_of_measure = models.CharField(max_length=20, blank=True)
    cost_center = models.ForeignKey(
        'labor.CostCenter', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='wip_entries',
    )
    routing_operation = models.ForeignKey(
        'pps.RoutingOperation', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='wip_entries',
    )
    source_movement = models.ForeignKey(
        'inventory.StockMovement', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='wip_entries',
    )
    source_labor_booking = models.ForeignKey(
        'labor.LaborBooking', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='wip_entries',
    )
    source_production_report = models.ForeignKey(
        'mes.ProductionReport', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='wip_entries',
    )
    source_overhead_allocation = models.ForeignKey(
        OverheadAllocation, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='wip_entries',
    )
    entry_date = models.DateTimeField(default=timezone.now)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='posted_wip_entries',
    )
    is_reversal = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-entry_date']
        unique_together = ('tenant', 'entry_number')
        indexes = [
            models.Index(fields=['tenant', 'job', '-entry_date']),
            models.Index(fields=['tenant', 'entry_type', '-entry_date']),
            models.Index(fields=['tenant', 'cost_center']),
            models.Index(fields=['tenant', 'routing_operation']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['source_movement', 'entry_type'],
                condition=models.Q(source_movement__isnull=False),
                name='cost_wip_unique_movement_type',
            ),
            models.UniqueConstraint(
                fields=['source_labor_booking', 'entry_type'],
                condition=models.Q(source_labor_booking__isnull=False),
                name='cost_wip_unique_labor_type',
            ),
            models.UniqueConstraint(
                fields=['source_production_report', 'entry_type'],
                condition=models.Q(source_production_report__isnull=False),
                name='cost_wip_unique_report_type',
            ),
            models.UniqueConstraint(
                fields=['source_overhead_allocation', 'entry_type'],
                condition=models.Q(source_overhead_allocation__isnull=False),
                name='cost_wip_unique_oha_type',
            ),
        ]

    def __str__(self):
        return f'{self.entry_number} | {self.entry_type} | {self.amount}'

    def save(self, *args, **kwargs):
        if not self.entry_number and self.tenant_id:
            last = (
                WIPEntry.all_objects
                .filter(tenant_id=self.tenant_id, entry_number__startswith='WIP-')
                .order_by('-entry_number').first()
            )
            n = 1
            if last and last.entry_number.startswith('WIP-'):
                try:
                    n = int(last.entry_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.entry_number = f'WIP-{n:05d}'
        super().save(*args, **kwargs)


# ============================================================================
# 12.2  ACTUAL COST TRACKING & VARIANCE
# ============================================================================

class ActualCost(TenantAwareModel, TimeStampedModel):
    """Computed actual-cost rollup snapshot per production order at a point in time.

    Idempotent — re-running the compute service overwrites the row for the
    given ``as_of_date``.
    """

    production_order = models.ForeignKey(
        'pps.ProductionOrder', on_delete=models.PROTECT, related_name='actual_costs',
    )
    as_of_date = models.DateField()
    material_cost = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    labor_cost = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    overhead_cost = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    total_cost = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    is_locked = models.BooleanField(default=False)
    computed_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-as_of_date']
        unique_together = ('production_order', 'as_of_date')
        indexes = [
            models.Index(fields=['tenant', 'production_order']),
        ]

    def __str__(self):
        return f'{self.production_order} @ {self.as_of_date} = {self.total_cost}'

    def save(self, *args, **kwargs):
        self.total_cost = (
            (self.material_cost or Decimal('0'))
            + (self.labor_cost or Decimal('0'))
            + (self.overhead_cost or Decimal('0'))
        )
        super().save(*args, **kwargs)


class CostVariance(TenantAwareModel, TimeStampedModel):
    """Per-PO 6-axis variance breakdown vs. standard.

    Convention: positive = unfavorable (actual > standard); negative = favorable.
    """

    variance_number = models.CharField(max_length=15)
    production_order = models.ForeignKey(
        'pps.ProductionOrder', on_delete=models.PROTECT, related_name='cost_variances',
    )
    version = models.ForeignKey(
        StandardCostVersion, on_delete=models.PROTECT, related_name='variances',
    )
    material_price_variance = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    material_usage_variance = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    labor_rate_variance = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    labor_efficiency_variance = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    overhead_spending_variance = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    overhead_volume_variance = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    total_variance = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    analysis_notes = models.TextField(blank=True)
    analyzed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='analyzed_variances',
    )
    analyzed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-analyzed_at']
        unique_together = (
            ('tenant', 'variance_number'),
            ('production_order', 'version'),
        )

    def __str__(self):
        return f'{self.variance_number} | {self.production_order} | total={self.total_variance}'

    def save(self, *args, **kwargs):
        if not self.variance_number and self.tenant_id:
            last = (
                CostVariance.all_objects
                .filter(tenant_id=self.tenant_id, variance_number__startswith='VAR-')
                .order_by('-variance_number').first()
            )
            n = 1
            if last and last.variance_number.startswith('VAR-'):
                try:
                    n = int(last.variance_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.variance_number = f'VAR-{n:05d}'
        self.total_variance = (
            (self.material_price_variance or Decimal('0'))
            + (self.material_usage_variance or Decimal('0'))
            + (self.labor_rate_variance or Decimal('0'))
            + (self.labor_efficiency_variance or Decimal('0'))
            + (self.overhead_spending_variance or Decimal('0'))
            + (self.overhead_volume_variance or Decimal('0'))
        )
        super().save(*args, **kwargs)


# ============================================================================
# 12.5  MANUFACTURING FINANCIAL REPORTS
# ============================================================================

class COGMReport(TenantAwareModel, TimeStampedModel):
    """Per-period Cost of Goods Manufactured.

    cogm = opening_wip + direct_materials + direct_labor + overhead_applied - closing_wip
    """

    report_number = models.CharField(max_length=15)
    period = models.OneToOneField(
        AccountingPeriod, on_delete=models.PROTECT, related_name='cogm_report',
    )
    opening_wip = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    direct_materials = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    direct_labor = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    overhead_applied = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    closing_wip = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    cogm = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    generated_at = models.DateTimeField(default=timezone.now)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='generated_cogm_reports',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-period__start_date']
        unique_together = ('tenant', 'report_number')

    def __str__(self):
        return f'{self.report_number} | {self.period.name} | COGM={self.cogm}'

    def save(self, *args, **kwargs):
        if not self.report_number and self.tenant_id:
            last = (
                COGMReport.all_objects
                .filter(tenant_id=self.tenant_id, report_number__startswith='COGM-')
                .order_by('-report_number').first()
            )
            n = 1
            if last and last.report_number.startswith('COGM-'):
                try:
                    n = int(last.report_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.report_number = f'COGM-{n:05d}'
        self.cogm = (
            (self.opening_wip or Decimal('0'))
            + (self.direct_materials or Decimal('0'))
            + (self.direct_labor or Decimal('0'))
            + (self.overhead_applied or Decimal('0'))
            - (self.closing_wip or Decimal('0'))
        )
        super().save(*args, **kwargs)


class GrossMarginReport(TenantAwareModel, TimeStampedModel):
    """Per-product per-period margin row.

    revenue       = units_completed x unit_sale_price
    cogs          = units_completed x actual_cost_per_unit
    gross_margin  = revenue - cogs
    margin_percent = gross_margin / revenue x 100  (0 when revenue == 0)
    """

    period = models.ForeignKey(
        AccountingPeriod, on_delete=models.PROTECT, related_name='margin_rows',
    )
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='margin_rows',
    )
    units_completed = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    standard_cost_per_unit = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    actual_cost_per_unit = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    unit_sale_price = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    revenue = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    cogs = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    gross_margin = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    margin_percent = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    generated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['period', '-gross_margin']
        unique_together = ('period', 'product')

    def __str__(self):
        return f'{self.period.name} | {self.product.sku} | margin={self.gross_margin}'

    def save(self, *args, **kwargs):
        units = self.units_completed or Decimal('0')
        self.revenue = (units * (self.unit_sale_price or Decimal('0'))).quantize(Decimal('0.01'))
        self.cogs = (units * (self.actual_cost_per_unit or Decimal('0'))).quantize(Decimal('0.01'))
        self.gross_margin = self.revenue - self.cogs
        if self.revenue and self.revenue != 0:
            self.margin_percent = (
                (self.gross_margin / self.revenue) * Decimal('100')
            ).quantize(Decimal('0.01'))
        else:
            self.margin_percent = Decimal('0')
        super().save(*args, **kwargs)


class PlantPnLReport(TenantAwareModel, TimeStampedModel):
    """Plant-level P&L per period (revenue - COGM - SG&A - unallocated overhead)."""

    period = models.OneToOneField(
        AccountingPeriod, on_delete=models.PROTECT, related_name='pnl_report',
    )
    revenue = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    cogm = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    gross_profit = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    selling_expense = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    general_admin_expense = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    unallocated_overhead = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    operating_income = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    generated_at = models.DateTimeField(default=timezone.now)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='generated_pnl_reports',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-period__start_date']

    def __str__(self):
        return f'P&L | {self.period.name} | OI={self.operating_income}'

    def save(self, *args, **kwargs):
        self.gross_profit = (self.revenue or Decimal('0')) - (self.cogm or Decimal('0'))
        self.operating_income = (
            self.gross_profit
            - (self.selling_expense or Decimal('0'))
            - (self.general_admin_expense or Decimal('0'))
            - (self.unallocated_overhead or Decimal('0'))
        )
        super().save(*args, **kwargs)
