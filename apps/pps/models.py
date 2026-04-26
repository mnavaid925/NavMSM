"""Module 4 — Production Planning & Scheduling.

Sub-modules:
    4.1  Master Production Schedule (MPS)        (DemandForecast,
                                                  MasterProductionSchedule, MPSLine)
    4.2  Capacity Planning                       (WorkCenter, CapacityCalendar,
                                                  CapacityLoad)
    4.3  Finite & Infinite Scheduling            (Routing, RoutingOperation,
                                                  ProductionOrder,
                                                  ScheduledOperation)
    4.4  What-If Simulation                      (Scenario, ScenarioChange,
                                                  ScenarioResult)
    4.5  Advanced Planning & Optimization        (OptimizationObjective,
                                                  OptimizationRun,
                                                  OptimizationResult)
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.bom.models import BillOfMaterials
from apps.core.models import TenantAwareModel, TimeStampedModel
from apps.plm.models import Product


# ============================================================================
# 4.1  MASTER PRODUCTION SCHEDULE (MPS)
# ============================================================================

class DemandForecast(TenantAwareModel, TimeStampedModel):
    """Forecasted demand for a product across a calendar period."""

    SOURCE_CHOICES = [
        ('manual', 'Manual Entry'),
        ('sales_order', 'Sales Order'),
        ('historical', 'Historical Trend'),
    ]

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='demand_forecasts',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    forecast_qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='manual')
    confidence_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('80'),
        help_text='Forecast confidence — 0-100.',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-period_start', 'product__sku']
        indexes = [models.Index(fields=['tenant', 'product', 'period_start'])]

    def __str__(self):
        return f'{self.product.sku} · {self.period_start:%Y-%m-%d} · {self.forecast_qty}'


class MasterProductionSchedule(TenantAwareModel, TimeStampedModel):
    """MPS header — covers a horizon split into time buckets (day/week/month)."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('released', 'Released'),
        ('obsolete', 'Obsolete'),
    ]
    BUCKET_CHOICES = [
        ('day', 'Daily'),
        ('week', 'Weekly'),
        ('month', 'Monthly'),
    ]

    mps_number = models.CharField(max_length=30)
    name = models.CharField(max_length=255)
    horizon_start = models.DateField()
    horizon_end = models.DateField()
    time_bucket = models.CharField(max_length=10, choices=BUCKET_CHOICES, default='week')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mps_created',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mps_approved',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'mps_number')
        verbose_name = 'Master Production Schedule'
        verbose_name_plural = 'Master Production Schedules'

    def __str__(self):
        return f'{self.mps_number} — {self.name}'

    def is_editable(self):
        return self.status in ('draft', 'under_review')


class MPSLine(TenantAwareModel, TimeStampedModel):
    """A single product/period row inside an MPS."""

    mps = models.ForeignKey(
        MasterProductionSchedule, on_delete=models.CASCADE, related_name='lines',
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='mps_lines',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    forecast_qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    firm_planned_qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    scheduled_qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    available_to_promise = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['mps', 'period_start', 'product__sku']
        unique_together = ('mps', 'product', 'period_start')
        verbose_name = 'MPS Line'

    def __str__(self):
        return f'{self.mps.mps_number} · {self.product.sku} · {self.period_start:%Y-%m-%d}'


# ============================================================================
# 4.2  CAPACITY PLANNING
# ============================================================================

class WorkCenter(TenantAwareModel, TimeStampedModel):
    """A resource (machine / labor pool / cell / line) that performs operations."""

    TYPE_CHOICES = [
        ('machine', 'Machine'),
        ('labor', 'Labor Pool'),
        ('cell', 'Cell'),
        ('assembly_line', 'Assembly Line'),
    ]

    code = models.CharField(max_length=40)
    name = models.CharField(max_length=255)
    work_center_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='machine')
    capacity_per_hour = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('1'),
        help_text='Throughput target in units/hour at 100% efficiency.',
    )
    efficiency_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('100'),
        help_text='Realized efficiency — 0-100.',
    )
    cost_per_hour = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0'),
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} — {self.name}'


class CapacityCalendar(TenantAwareModel, TimeStampedModel):
    """One row per shift per weekday for a work center."""

    DAY_CHOICES = [
        (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'),
        (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
    ]

    work_center = models.ForeignKey(
        WorkCenter, on_delete=models.CASCADE, related_name='calendars',
    )
    day_of_week = models.PositiveSmallIntegerField(choices=DAY_CHOICES, default=0)
    shift_start = models.TimeField()
    shift_end = models.TimeField()
    is_working = models.BooleanField(default=True)

    class Meta:
        ordering = ['work_center', 'day_of_week', 'shift_start']
        unique_together = ('work_center', 'day_of_week', 'shift_start')
        verbose_name = 'Capacity Calendar Entry'
        verbose_name_plural = 'Capacity Calendar'

    def __str__(self):
        return f'{self.work_center.code} · {self.get_day_of_week_display()} {self.shift_start:%H:%M}-{self.shift_end:%H:%M}'

    def shift_minutes(self):
        if not self.is_working:
            return 0
        s = self.shift_start.hour * 60 + self.shift_start.minute
        e = self.shift_end.hour * 60 + self.shift_end.minute
        return max(0, e - s)


class CapacityLoad(TenantAwareModel, TimeStampedModel):
    """Computed snapshot of load vs available capacity per work center per day."""

    work_center = models.ForeignKey(
        WorkCenter, on_delete=models.CASCADE, related_name='load_snapshots',
    )
    period_date = models.DateField()
    available_minutes = models.PositiveIntegerField(default=0)
    planned_minutes = models.PositiveIntegerField(default=0)
    utilization_pct = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'))
    is_bottleneck = models.BooleanField(default=False)
    computed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['work_center', 'period_date']
        unique_together = ('work_center', 'period_date')
        verbose_name = 'Capacity Load'

    def __str__(self):
        return f'{self.work_center.code} · {self.period_date} · {self.utilization_pct}%'

    def is_stale(self):
        return self.computed_at is None


# ============================================================================
# 4.3  FINITE & INFINITE SCHEDULING
# ============================================================================

class Routing(TenantAwareModel, TimeStampedModel):
    """Sequence of operations needed to manufacture a product."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('obsolete', 'Obsolete'),
    ]

    routing_number = models.CharField(max_length=30)
    name = models.CharField(max_length=255, blank=True)
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='routings',
    )
    version = models.CharField(max_length=10, default='A')
    is_default = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='routings_created',
    )

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'product', 'version')

    def __str__(self):
        return f'{self.routing_number} — {self.product.sku} v{self.version}'


class RoutingOperation(TenantAwareModel, TimeStampedModel):
    """A single operation step inside a routing."""

    routing = models.ForeignKey(
        Routing, on_delete=models.CASCADE, related_name='operations',
    )
    sequence = models.PositiveIntegerField(default=10)
    operation_name = models.CharField(max_length=255)
    work_center = models.ForeignKey(
        WorkCenter, on_delete=models.PROTECT, related_name='routing_operations',
    )
    setup_minutes = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    run_minutes_per_unit = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('0'))
    queue_minutes = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    move_minutes = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    instructions = models.TextField(blank=True)

    class Meta:
        ordering = ['routing', 'sequence']
        verbose_name = 'Routing Operation'

    def __str__(self):
        return f'{self.routing.routing_number} · {self.sequence:03d} · {self.operation_name}'

    def total_minutes(self, quantity):
        """Setup + run × qty + queue + move."""
        run = self.run_minutes_per_unit * Decimal(str(quantity))
        return self.setup_minutes + run + self.queue_minutes + self.move_minutes


class ProductionOrder(TenantAwareModel, TimeStampedModel):
    """A discrete order to produce a quantity of a product."""

    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('released', 'Released'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('rush', 'Rush'),
    ]
    METHOD_CHOICES = [
        ('forward', 'Forward (from start)'),
        ('backward', 'Backward (from due date)'),
        ('infinite', 'Infinite (ignore capacity)'),
    ]

    order_number = models.CharField(max_length=30)
    mps_line = models.ForeignKey(
        MPSLine, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_orders',
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='production_orders',
    )
    routing = models.ForeignKey(
        Routing, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_orders',
    )
    bom = models.ForeignKey(
        BillOfMaterials, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_orders',
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('1'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    scheduling_method = models.CharField(max_length=10, choices=METHOD_CHOICES, default='forward')
    requested_start = models.DateTimeField(null=True, blank=True)
    requested_end = models.DateTimeField(null=True, blank=True)
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_orders_created',
    )

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'order_number')

    def __str__(self):
        return f'{self.order_number} — {self.product.sku} × {self.quantity}'

    def is_editable(self):
        return self.status in ('planned',)

    def can_release(self):
        return self.status == 'planned'

    def can_start(self):
        return self.status == 'released'

    def can_complete(self):
        return self.status == 'in_progress'


class ScheduledOperation(TenantAwareModel, TimeStampedModel):
    """A scheduled execution of a routing operation against a production order."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('skipped', 'Skipped'),
    ]

    production_order = models.ForeignKey(
        ProductionOrder, on_delete=models.CASCADE, related_name='scheduled_operations',
    )
    routing_operation = models.ForeignKey(
        RoutingOperation, on_delete=models.PROTECT,
        related_name='scheduled_operations', null=True, blank=True,
    )
    work_center = models.ForeignKey(
        WorkCenter, on_delete=models.PROTECT, related_name='scheduled_operations',
    )
    sequence = models.PositiveIntegerField(default=10)
    operation_name = models.CharField(max_length=255, blank=True)
    planned_start = models.DateTimeField()
    planned_end = models.DateTimeField()
    planned_minutes = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['production_order', 'sequence']
        indexes = [
            models.Index(fields=['tenant', 'work_center', 'planned_start']),
        ]
        verbose_name = 'Scheduled Operation'

    def __str__(self):
        return f'{self.production_order.order_number} · op {self.sequence} @ {self.work_center.code}'


# ============================================================================
# 4.4  WHAT-IF SIMULATION
# ============================================================================

class Scenario(TenantAwareModel, TimeStampedModel):
    """A what-if simulation cloned from an existing MPS."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('applied', 'Applied'),
        ('discarded', 'Discarded'),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    base_mps = models.ForeignKey(
        MasterProductionSchedule, on_delete=models.PROTECT, related_name='scenarios',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scenarios_created',
    )
    ran_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scenarios_applied',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def is_editable(self):
        return self.status in ('draft', 'completed')


class ScenarioChange(TenantAwareModel, TimeStampedModel):
    """One change applied to the base MPS as part of a scenario."""

    CHANGE_TYPE_CHOICES = [
        ('add_order', 'Add Order'),
        ('remove_order', 'Remove Order'),
        ('change_qty', 'Change Quantity'),
        ('change_date', 'Change Date'),
        ('change_priority', 'Change Priority'),
        ('shift_resource', 'Shift Resource'),
    ]

    scenario = models.ForeignKey(
        Scenario, on_delete=models.CASCADE, related_name='changes',
    )
    change_type = models.CharField(max_length=20, choices=CHANGE_TYPE_CHOICES, default='change_qty')
    target_ref = models.CharField(
        max_length=120,
        help_text='Reference to the target (e.g. mps_line:42).',
    )
    payload = models.JSONField(default=dict, blank=True)
    sequence = models.PositiveIntegerField(default=10)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['scenario', 'sequence']
        verbose_name = 'Scenario Change'


    def __str__(self):
        return f'{self.scenario.name} · {self.get_change_type_display()} · {self.target_ref}'


class ScenarioResult(TenantAwareModel, TimeStampedModel):
    """KPI snapshot captured after running a scenario."""

    scenario = models.OneToOneField(
        Scenario, on_delete=models.CASCADE, related_name='result',
    )
    on_time_pct = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'))
    total_load_minutes = models.PositiveIntegerField(default=0)
    total_idle_minutes = models.PositiveIntegerField(default=0)
    bottleneck_count = models.PositiveIntegerField(default=0)
    summary_json = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-computed_at']

    def __str__(self):
        return f'{self.scenario.name} result · {self.on_time_pct}% OT'


# ============================================================================
# 4.5  ADVANCED PLANNING & OPTIMIZATION (APO)
# ============================================================================

class OptimizationObjective(TenantAwareModel, TimeStampedModel):
    """Weighted goal definition used by the optimizer.

    The v1 optimizer is a deterministic greedy heuristic — see
    apps/pps/services/optimizer.py. Trained ML models are out of scope for
    Phase 1; this model layer is forward-compatible with one.
    """

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    weight_changeovers = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('1'),
        help_text='Relative penalty for grouping unlike products together.',
    )
    weight_idle = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('1'),
        help_text='Relative penalty for idle time on work centers.',
    )
    weight_lateness = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('2'),
        help_text='Relative penalty for missing requested due dates.',
    )
    weight_priority = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('1.5'),
        help_text='Relative reward for honoring priority on rush orders.',
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'name')
        verbose_name = 'Optimization Objective'

    def __str__(self):
        return self.name


class OptimizationRun(TenantAwareModel, TimeStampedModel):
    """A single execution of the optimizer against an MPS."""

    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    name = models.CharField(max_length=255)
    mps = models.ForeignKey(
        MasterProductionSchedule, on_delete=models.PROTECT, related_name='optimization_runs',
    )
    objective = models.ForeignKey(
        OptimizationObjective, on_delete=models.PROTECT, related_name='runs',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='optimization_runs_started',
    )
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Optimization Run'

    def __str__(self):
        return f'{self.name} ({self.get_status_display()})'


class OptimizationResult(TenantAwareModel, TimeStampedModel):
    """Before/after KPIs produced by an optimization run."""

    run = models.OneToOneField(
        OptimizationRun, on_delete=models.CASCADE, related_name='result',
    )
    before_total_minutes = models.PositiveIntegerField(default=0)
    after_total_minutes = models.PositiveIntegerField(default=0)
    before_changeovers = models.PositiveIntegerField(default=0)
    after_changeovers = models.PositiveIntegerField(default=0)
    before_lateness = models.PositiveIntegerField(default=0)
    after_lateness = models.PositiveIntegerField(default=0)
    improvement_pct = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'))
    suggestion_json = models.JSONField(default=dict, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='optimization_results_applied',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Optimization Result'

    def __str__(self):
        return f'{self.run.name} result · {self.improvement_pct}% gain'
