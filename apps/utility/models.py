"""Module 14 - Energy & Utility Management.

Sub-modules:
    14.1  Utility Meter Integration         (UtilityType, UtilityMeter,
                                             UtilityConsumption)
    14.2  Energy Cost Allocation            (UtilityTariff, UtilityAllocation)
    14.3  Peak Demand Management            (TOURateBand, DemandResponseEvent,
                                             PeakShavingSuggestion)
    14.4  Carbon & Sustainability Reporting (EmissionFactor, CarbonEmission,
                                             SustainabilityKPI)
    14.5  Utility Benchmarking              (BenchmarkSnapshot,
                                             BenchmarkComparison)

Cross-module integration (additive, no schema changes to other apps):
    - apps.eam.AssetMeterReading.post_save (meter_type='kwh') -> UtilityConsumption
    - apps.utility.UtilityConsumption.post_save              -> CarbonEmission
    - apps.utility.UtilityAllocation.post_allocation()        -> cost.DriverActuals

Lessons applied:
    * L-01 unique_together with tenant excluded -> form-level clean()
    * L-02 every Decimal carries explicit MinValueValidator
    * L-03 view+template status gate parity via is_*() helpers
    * L-12 auto-numbering retry loop in views (mirrors cost pattern)
    * L-13 transaction.atomic() around denorm bumps
    * L-14 per-workflow forms enforce required fields
    * L-17 PROTECT on audit-trail children (CarbonEmission.factor,
            UtilityConsumption.meter, UtilityAllocation.period)
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel


# Common decimal validator constants (mirrors apps/cost/models.py).
NEG_BOUND = Decimal('-99999999.9999')
NON_NEG = MinValueValidator(Decimal('0'))
SIGNED = MinValueValidator(NEG_BOUND)
PCT_MAX = MaxValueValidator(Decimal('100'))


# ============================================================================
# 14.1  UTILITY METER INTEGRATION
# ============================================================================

class UtilityType(TenantAwareModel, TimeStampedModel):
    """Tenant catalog of utility types (electricity / water / natural_gas / ...).

    Optional FK to ``cost.CostDriver`` lets the allocation service emit a
    matching ``cost.DriverActuals`` row so existing
    ``cost.services.overhead.apply_overhead(period)`` sweeps utility cost
    into the Utilities pool automatically.
    """

    UNIT_CHOICES = [
        ('kwh', 'kWh'),
        ('m3', 'Cubic Metres'),
        ('l', 'Litres'),
        ('kg', 'Kilograms'),
        ('scfm', 'Standard CFM'),
        ('therm', 'Therms'),
    ]

    code = models.SlugField(max_length=30)
    name = models.CharField(max_length=120)
    unit_of_measure = models.CharField(max_length=10, choices=UNIT_CHOICES, default='kwh')
    cost_driver = models.ForeignKey(
        'cost.CostDriver', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='utility_types',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class UtilityMeter(TenantAwareModel, TimeStampedModel):
    """Physical meter or sub-meter.

    Auto-numbered ``MTR-00001``. Supports a self-referencing parent_meter
    hierarchy for sub-metering. Optional FK to ``eam.Asset`` enables the
    cross-module auto-feed signal from ``eam.AssetMeterReading``.
    """

    meter_number = models.CharField(max_length=15)
    utility_type = models.ForeignKey(
        UtilityType, on_delete=models.PROTECT, related_name='meters',
    )
    name = models.CharField(max_length=120)
    location = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='utility_meters',
    )
    parent_meter = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sub_meters',
    )
    cost_center = models.ForeignKey(
        'labor.CostCenter', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='utility_meters',
    )
    asset = models.ForeignKey(
        'eam.Asset', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='utility_meters',
    )
    installed_at = models.DateField(null=True, blank=True)
    last_calibrated_at = models.DateField(null=True, blank=True)
    multiplier = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal('1.0000'), validators=[NON_NEG],
        help_text='Reading multiplier for transformers / scaling factors.',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['meter_number']
        unique_together = (
            ('tenant', 'meter_number'),
            ('tenant', 'utility_type', 'name'),
        )
        indexes = [
            models.Index(fields=['tenant', 'utility_type', 'is_active']),
            models.Index(fields=['tenant', 'asset']),
        ]

    def __str__(self):
        return f'{self.meter_number} - {self.name}'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.meter_number and self.tenant_id:
            last = (
                UtilityMeter.all_objects
                .filter(tenant_id=self.tenant_id, meter_number__startswith='MTR-')
                .order_by('-meter_number').first()
            )
            n = 1
            if last and last.meter_number.startswith('MTR-'):
                try:
                    n = int(last.meter_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.meter_number = f'MTR-{n:05d}'
        super().save(*args, **kwargs)


class UtilityConsumption(TenantAwareModel, TimeStampedModel):
    """Append-only meter consumption ledger.

    consumption  = (end_reading - start_reading) * meter.multiplier  (computed in save)
    total_cost   = consumption * unit_cost                          (computed in save)

    ``source_meter_reading`` is unique (when set) so the EAM auto-feed signal
    is idempotent — a second post_save on the same AssetMeterReading is a no-op.
    """

    SOURCE_CHOICES = [
        ('manual', 'Manual Entry'),
        ('eam_meter', 'EAM Meter Reading'),
        ('iot', 'IoT Sensor'),
        ('billing_import', 'Billing Import'),
    ]

    entry_number = models.CharField(max_length=15)
    meter = models.ForeignKey(
        UtilityMeter, on_delete=models.PROTECT, related_name='consumptions',
    )
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    start_reading = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    end_reading = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    consumption = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=6, default=Decimal('0'), validators=[NON_NEG],
    )
    total_cost = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    source = models.CharField(max_length=15, choices=SOURCE_CHOICES, default='manual')
    source_meter_reading = models.ForeignKey(
        'eam.AssetMeterReading', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='utility_consumptions',
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='recorded_utility_consumptions',
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    is_reversal = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-period_start']
        unique_together = ('tenant', 'entry_number')
        indexes = [
            models.Index(fields=['tenant', 'meter', '-period_start']),
            models.Index(fields=['tenant', 'source']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['source_meter_reading'],
                condition=models.Q(source_meter_reading__isnull=False),
                name='utility_consumption_unique_meter_reading',
            ),
        ]

    def __str__(self):
        return f'{self.entry_number} | {self.meter.meter_number} | {self.consumption}'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.entry_number and self.tenant_id:
            last = (
                UtilityConsumption.all_objects
                .filter(tenant_id=self.tenant_id, entry_number__startswith='UC-')
                .order_by('-entry_number').first()
            )
            n = 1
            if last and last.entry_number.startswith('UC-'):
                try:
                    n = int(last.entry_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.entry_number = f'UC-{n:05d}'
        # Compute consumption from delta * meter multiplier
        delta = (self.end_reading or Decimal('0')) - (self.start_reading or Decimal('0'))
        if delta < 0:
            delta = Decimal('0')
        mult = Decimal('1')
        if self.meter_id:
            try:
                mult = self.meter.multiplier or Decimal('1')
            except UtilityMeter.DoesNotExist:
                mult = Decimal('1')
        self.consumption = (delta * mult).quantize(Decimal('0.0001'))
        # Compute total_cost
        self.total_cost = (
            self.consumption * (self.unit_cost or Decimal('0'))
        ).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)


# ============================================================================
# 14.2  ENERGY COST ALLOCATION
# ============================================================================

class UtilityTariff(TenantAwareModel, TimeStampedModel):
    """Effective-dated price-per-unit per utility type.

    ``flat_rate`` is the fall-back; if ``TOURateBand`` rows exist for this
    tariff they take precedence at billing time.
    """

    tariff_number = models.CharField(max_length=15)
    utility_type = models.ForeignKey(
        UtilityType, on_delete=models.PROTECT, related_name='tariffs',
    )
    name = models.CharField(max_length=120)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    flat_rate = models.DecimalField(
        max_digits=12, decimal_places=6, default=Decimal('0'), validators=[NON_NEG],
        help_text='Fall-back price per unit when no TOU bands match.',
    )
    currency = models.CharField(max_length=3, default='USD')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-effective_from', 'tariff_number']
        unique_together = ('tenant', 'tariff_number')
        indexes = [
            models.Index(fields=['tenant', 'utility_type', 'is_active']),
        ]

    def __str__(self):
        return f'{self.tariff_number} - {self.name}'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.tariff_number and self.tenant_id:
            last = (
                UtilityTariff.all_objects
                .filter(tenant_id=self.tenant_id, tariff_number__startswith='TRF-')
                .order_by('-tariff_number').first()
            )
            n = 1
            if last and last.tariff_number.startswith('TRF-'):
                try:
                    n = int(last.tariff_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.tariff_number = f'TRF-{n:05d}'
        super().save(*args, **kwargs)


class UtilityAllocation(TenantAwareModel, TimeStampedModel):
    """Period-scoped distribution of metered cost into cost centers / products / POs.

    When ``is_posted_to_cost`` is True, ``services/allocation.post_allocation``
    has emitted a matching ``cost.DriverActuals`` row so the existing overhead
    pipeline picks it up.
    """

    METHOD_CHOICES = [
        ('meter_consumption', 'Meter Consumption'),
        ('production_volume', 'Production Volume'),
        ('floor_area', 'Floor Area'),
        ('direct_assignment', 'Direct Assignment'),
    ]

    allocation_number = models.CharField(max_length=15)
    period = models.ForeignKey(
        'cost.AccountingPeriod', on_delete=models.PROTECT,
        related_name='utility_allocations',
    )
    meter = models.ForeignKey(
        UtilityMeter, on_delete=models.PROTECT, related_name='allocations',
    )
    target_cost_center = models.ForeignKey(
        'labor.CostCenter', on_delete=models.PROTECT,
        null=True, blank=True, related_name='utility_allocations',
    )
    target_product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT,
        null=True, blank=True, related_name='utility_allocations',
    )
    target_production_order = models.ForeignKey(
        'pps.ProductionOrder', on_delete=models.PROTECT,
        null=True, blank=True, related_name='utility_allocations',
    )
    allocation_method = models.CharField(
        max_length=20, choices=METHOD_CHOICES, default='meter_consumption',
    )
    share_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('100'),
        validators=[NON_NEG, PCT_MAX],
        help_text='Percentage of meter cost allocated to this target (0-100).',
    )
    allocated_consumption = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    allocated_cost = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    is_posted_to_cost = models.BooleanField(default=False)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='posted_utility_allocations',
    )
    is_reversed = models.BooleanField(default=False)
    reversal_reason = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-posted_at', 'allocation_number']
        unique_together = ('tenant', 'allocation_number')
        indexes = [
            models.Index(fields=['tenant', 'period', 'meter']),
            models.Index(fields=['tenant', 'target_cost_center']),
            models.Index(fields=['tenant', 'target_product']),
            models.Index(fields=['tenant', 'target_production_order']),
        ]

    def __str__(self):
        target = (
            self.target_production_order
            or self.target_product
            or self.target_cost_center
            or 'unallocated'
        )
        return f'{self.allocation_number} | {self.meter.meter_number} | {target}'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.allocation_number and self.tenant_id:
            last = (
                UtilityAllocation.all_objects
                .filter(tenant_id=self.tenant_id, allocation_number__startswith='UAL-')
                .order_by('-allocation_number').first()
            )
            n = 1
            if last and last.allocation_number.startswith('UAL-'):
                try:
                    n = int(last.allocation_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.allocation_number = f'UAL-{n:05d}'
        super().save(*args, **kwargs)


# ============================================================================
# 14.3  PEAK DEMAND MANAGEMENT
# ============================================================================

class TOURateBand(TenantAwareModel, TimeStampedModel):
    """Time-of-Use rate band attached to a tariff.

    day_of_week: 0=Mon, ..., 6=Sun, or 'all'.
    """

    BAND_CHOICES = [
        ('peak', 'Peak'),
        ('shoulder', 'Shoulder'),
        ('off_peak', 'Off-Peak'),
    ]
    DAY_CHOICES = [
        ('all', 'All Days'),
        ('weekday', 'Weekdays (Mon-Fri)'),
        ('weekend', 'Weekends (Sat-Sun)'),
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ]

    tariff = models.ForeignKey(
        UtilityTariff, on_delete=models.CASCADE, related_name='tou_bands',
    )
    band_type = models.CharField(max_length=10, choices=BAND_CHOICES, default='peak')
    day_of_week = models.CharField(max_length=10, choices=DAY_CHOICES, default='weekday')
    start_time = models.TimeField()
    end_time = models.TimeField()
    rate = models.DecimalField(
        max_digits=12, decimal_places=6, validators=[NON_NEG],
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['tariff', 'day_of_week', 'start_time']
        unique_together = ('tariff', 'band_type', 'day_of_week', 'start_time')

    def __str__(self):
        return f'{self.tariff.tariff_number} | {self.band_type} | {self.day_of_week} {self.start_time}-{self.end_time}'


class DemandResponseEvent(TenantAwareModel, TimeStampedModel):
    """Utility-declared curtailment window.

    Workflow: scheduled -> active -> completed | cancelled.
    """

    EVENT_TYPE_CHOICES = [
        ('mandatory', 'Mandatory'),
        ('voluntary', 'Voluntary'),
        ('advisory', 'Advisory'),
    ]
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    SOURCE_CHOICES = [
        ('utility_provider', 'Utility Provider'),
        ('manual', 'Manual'),
    ]

    event_number = models.CharField(max_length=15)
    utility_type = models.ForeignKey(
        UtilityType, on_delete=models.PROTECT, related_name='dr_events',
    )
    event_type = models.CharField(max_length=10, choices=EVENT_TYPE_CHOICES, default='voluntary')
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    target_reduction_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('0'),
        validators=[NON_NEG, PCT_MAX],
    )
    incentive_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, validators=[NON_NEG],
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='scheduled')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='manual')
    cancellation_reason = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_dr_events',
    )

    class Meta:
        ordering = ['-start_at']
        unique_together = ('tenant', 'event_number')
        indexes = [
            models.Index(fields=['tenant', 'status', 'start_at']),
        ]

    def __str__(self):
        return f'{self.event_number} | {self.utility_type.code} | {self.status}'

    def is_activatable(self) -> bool:
        return self.status == 'scheduled'

    def is_completable(self) -> bool:
        return self.status == 'active'

    def is_cancellable(self) -> bool:
        return self.status in ('scheduled', 'active')

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.event_number and self.tenant_id:
            last = (
                DemandResponseEvent.all_objects
                .filter(tenant_id=self.tenant_id, event_number__startswith='DRE-')
                .order_by('-event_number').first()
            )
            n = 1
            if last and last.event_number.startswith('DRE-'):
                try:
                    n = int(last.event_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.event_number = f'DRE-{n:05d}'
        super().save(*args, **kwargs)


class PeakShavingSuggestion(TenantAwareModel, TimeStampedModel):
    """Read-only recommendation for an operation overlapping a peak window.

    Workflow: new -> acknowledged -> dismissed. Never mutates pps schedule.
    """

    STATUS_CHOICES = [
        ('new', 'New'),
        ('acknowledged', 'Acknowledged'),
        ('dismissed', 'Dismissed'),
    ]

    suggestion_number = models.CharField(max_length=15)
    event = models.ForeignKey(
        DemandResponseEvent, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='shaving_suggestions',
    )
    tou_band = models.ForeignKey(
        TOURateBand, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='shaving_suggestions',
    )
    production_order = models.ForeignKey(
        'pps.ProductionOrder', on_delete=models.PROTECT,
        related_name='shaving_suggestions',
    )
    scheduled_operation = models.ForeignKey(
        'pps.ScheduledOperation', on_delete=models.PROTECT,
        related_name='shaving_suggestions',
    )
    original_start = models.DateTimeField()
    original_end = models.DateTimeField()
    suggested_start = models.DateTimeField(null=True, blank=True)
    suggested_end = models.DateTimeField(null=True, blank=True)
    estimated_savings = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='new')
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='acknowledged_suggestions',
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    dismiss_reason = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-original_start']
        unique_together = ('tenant', 'suggestion_number')
        indexes = [
            models.Index(fields=['tenant', 'status', 'original_start']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['scheduled_operation', 'event'],
                condition=models.Q(event__isnull=False),
                name='utility_pss_unique_op_event',
            ),
            models.UniqueConstraint(
                fields=['scheduled_operation', 'tou_band'],
                condition=models.Q(tou_band__isnull=False) & models.Q(event__isnull=True),
                name='utility_pss_unique_op_band',
            ),
        ]

    def __str__(self):
        return f'{self.suggestion_number} | op#{self.scheduled_operation_id} | {self.status}'

    def is_acknowledgable(self) -> bool:
        return self.status == 'new'

    def is_dismissable(self) -> bool:
        return self.status in ('new', 'acknowledged')

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.suggestion_number and self.tenant_id:
            last = (
                PeakShavingSuggestion.all_objects
                .filter(tenant_id=self.tenant_id, suggestion_number__startswith='PSS-')
                .order_by('-suggestion_number').first()
            )
            n = 1
            if last and last.suggestion_number.startswith('PSS-'):
                try:
                    n = int(last.suggestion_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.suggestion_number = f'PSS-{n:05d}'
        super().save(*args, **kwargs)


# ============================================================================
# 14.4  CARBON & SUSTAINABILITY REPORTING
# ============================================================================

class EmissionFactor(TenantAwareModel, TimeStampedModel):
    """CO2-equivalent factor catalog per source per scope per region.

    Snapshot pattern: each CarbonEmission row keeps an FK to the factor it
    used so the regulator can audit which factor was current at the time of
    the emission. PROTECT against accidental delete.
    """

    SCOPE_CHOICES = [
        ('scope_1', 'Scope 1 - Direct'),
        ('scope_2', 'Scope 2 - Energy Indirect'),
        ('scope_3', 'Scope 3 - Other Indirect'),
    ]
    SOURCE_TYPE_CHOICES = [
        ('electricity_grid', 'Electricity (Grid)'),
        ('natural_gas', 'Natural Gas'),
        ('fuel_oil', 'Fuel Oil'),
        ('diesel', 'Diesel'),
        ('petrol', 'Petrol'),
        ('steam', 'Steam'),
        ('water', 'Water'),
        ('refrigerant', 'Refrigerant Leakage'),
        ('employee_commute', 'Employee Commute'),
        ('business_travel', 'Business Travel'),
        ('waste', 'Waste'),
        ('supply_chain', 'Supply Chain'),
    ]
    UNIT_CHOICES = [
        ('kwh', 'kWh'),
        ('m3', 'Cubic Metres'),
        ('l', 'Litres'),
        ('kg', 'Kilograms'),
        ('km', 'Kilometres'),
        ('usd', 'USD Spend'),
    ]

    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES)
    scope = models.CharField(max_length=8, choices=SCOPE_CHOICES, default='scope_2')
    region = models.CharField(max_length=3, blank=True, help_text='ISO 3166-1 alpha-3 country code, optional.')
    factor = models.DecimalField(
        max_digits=12, decimal_places=6, validators=[NON_NEG],
        help_text='kgCO2e per unit_of_measure.',
    )
    unit_of_measure = models.CharField(max_length=10, choices=UNIT_CHOICES, default='kwh')
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    source_reference = models.TextField(
        blank=True,
        help_text='IPCC / GHG-Protocol / EPA / DEFRA citation for audit trail.',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['scope', 'source_type', '-effective_from']
        unique_together = ('tenant', 'source_type', 'scope', 'region', 'effective_from')
        indexes = [
            models.Index(fields=['tenant', 'source_type', 'is_active']),
            models.Index(fields=['tenant', 'scope']),
        ]

    def __str__(self):
        region = self.region or 'global'
        return f'{self.source_type}/{self.scope}/{region} = {self.factor} kgCO2e/{self.unit_of_measure}'


class CarbonEmission(TenantAwareModel, TimeStampedModel):
    """Append-only ledger of CO2-equivalent emissions per period.

    Auto-emitted via signal from UtilityConsumption.post_save when an active
    EmissionFactor exists. Idempotent on (source_consumption,) unique
    constraint. PROTECT on factor FK preserves the regulator audit trail.
    """

    SCOPE_CHOICES = EmissionFactor.SCOPE_CHOICES

    entry_number = models.CharField(max_length=15)
    period = models.ForeignKey(
        'cost.AccountingPeriod', on_delete=models.PROTECT, related_name='carbon_emissions',
    )
    scope = models.CharField(max_length=8, choices=SCOPE_CHOICES, default='scope_2')
    source_type = models.CharField(max_length=20, choices=EmissionFactor.SOURCE_TYPE_CHOICES)
    source_quantity = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    factor = models.ForeignKey(
        EmissionFactor, on_delete=models.PROTECT, related_name='emissions',
    )
    co2e_kg = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    source_consumption = models.ForeignKey(
        UtilityConsumption, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='carbon_emissions',
    )
    source_allocation = models.ForeignKey(
        UtilityAllocation, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='carbon_emissions',
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='recorded_emissions',
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    is_reversal = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-recorded_at']
        unique_together = ('tenant', 'entry_number')
        indexes = [
            models.Index(fields=['tenant', 'period', 'scope']),
            models.Index(fields=['tenant', 'source_type']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['source_consumption'],
                condition=models.Q(source_consumption__isnull=False),
                name='utility_carbon_unique_consumption',
            ),
        ]

    def __str__(self):
        return f'{self.entry_number} | {self.scope} | {self.co2e_kg} kgCO2e'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.entry_number and self.tenant_id:
            last = (
                CarbonEmission.all_objects
                .filter(tenant_id=self.tenant_id, entry_number__startswith='CE-')
                .order_by('-entry_number').first()
            )
            n = 1
            if last and last.entry_number.startswith('CE-'):
                try:
                    n = int(last.entry_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.entry_number = f'CE-{n:05d}'
        # co2e_kg = source_quantity * factor.factor
        if self.factor_id:
            try:
                f_val = self.factor.factor or Decimal('0')
            except EmissionFactor.DoesNotExist:
                f_val = Decimal('0')
            self.co2e_kg = (
                (self.source_quantity or Decimal('0')) * f_val
            ).quantize(Decimal('0.0001'))
        super().save(*args, **kwargs)


class SustainabilityKPI(TenantAwareModel, TimeStampedModel):
    """Per-period snapshot of headline ESG KPIs (drives the dashboard)."""

    period = models.ForeignKey(
        'cost.AccountingPeriod', on_delete=models.PROTECT, related_name='sustainability_kpis',
    )
    total_scope_1_kg = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    total_scope_2_kg = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    total_scope_3_kg = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    total_co2e_kg = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    total_kwh = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    total_water_m3 = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    total_gas_m3 = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    total_units_produced = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    kwh_per_unit_produced = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    co2e_per_unit_produced = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    generated_at = models.DateTimeField(default=timezone.now)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='generated_sustainability_kpis',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-period__start_date']
        unique_together = ('tenant', 'period')

    def __str__(self):
        return f'KPI | {self.period.name} | {self.total_co2e_kg} kgCO2e'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        self.total_co2e_kg = (
            (self.total_scope_1_kg or Decimal('0'))
            + (self.total_scope_2_kg or Decimal('0'))
            + (self.total_scope_3_kg or Decimal('0'))
        )
        units = self.total_units_produced or Decimal('0')
        if units > 0:
            self.kwh_per_unit_produced = (
                (self.total_kwh or Decimal('0')) / units
            ).quantize(Decimal('0.0001'))
            self.co2e_per_unit_produced = (
                self.total_co2e_kg / units
            ).quantize(Decimal('0.0001'))
        else:
            self.kwh_per_unit_produced = Decimal('0')
            self.co2e_per_unit_produced = Decimal('0')
        super().save(*args, **kwargs)


# ============================================================================
# 14.5  UTILITY BENCHMARKING
# ============================================================================

class BenchmarkSnapshot(TenantAwareModel, TimeStampedModel):
    """Per-period per-plant efficiency snapshot.

    Drives plant-to-plant comparison. Anonymized industry-average rows are
    materialized with tenant=NULL, plant_label='industry_avg' by a
    superuser-only management command (cross-tenant aggregate; never exposes
    raw per-tenant data).
    """

    # Override tenant FK to allow NULL for the industry-average row.
    tenant = models.ForeignKey(
        'core.Tenant', on_delete=models.CASCADE,
        null=True, blank=True, related_name='benchmark_snapshots',
    )

    period = models.ForeignKey(
        'cost.AccountingPeriod', on_delete=models.PROTECT, related_name='benchmark_snapshots',
    )
    plant_label = models.CharField(max_length=60, default='main_factory')
    total_kwh = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    total_water_m3 = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    total_gas_m3 = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    total_co2e_kg = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    total_cost = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    total_units_produced = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    kwh_per_unit = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    water_per_unit = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    co2e_per_unit = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    cost_per_unit = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    generated_at = models.DateTimeField(default=timezone.now)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='generated_benchmark_snapshots',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-period__start_date', 'plant_label']
        unique_together = ('tenant', 'period', 'plant_label')

    def __str__(self):
        scope = self.tenant.slug if self.tenant_id else 'industry_avg'
        return f'{scope} | {self.period.name} | {self.plant_label}'

    def save(self, *args, **kwargs):
        # NOTE: tenant override allowed (NULL for industry_avg rows).
        units = self.total_units_produced or Decimal('0')
        if units > 0:
            self.kwh_per_unit = (
                (self.total_kwh or Decimal('0')) / units
            ).quantize(Decimal('0.0001'))
            self.water_per_unit = (
                (self.total_water_m3 or Decimal('0')) / units
            ).quantize(Decimal('0.0001'))
            self.co2e_per_unit = (
                (self.total_co2e_kg or Decimal('0')) / units
            ).quantize(Decimal('0.0001'))
            self.cost_per_unit = (
                (self.total_cost or Decimal('0')) / units
            ).quantize(Decimal('0.0001'))
        else:
            self.kwh_per_unit = Decimal('0')
            self.water_per_unit = Decimal('0')
            self.co2e_per_unit = Decimal('0')
            self.cost_per_unit = Decimal('0')
        super().save(*args, **kwargs)


class BenchmarkComparison(TenantAwareModel, TimeStampedModel):
    """One-shot comparison report between two snapshots."""

    COMPARISON_CHOICES = [
        ('plant_to_plant', 'Plant-to-Plant'),
        ('period_over_period', 'Period-over-Period'),
        ('tenant_to_tenant', 'Tenant vs. Industry Average'),
    ]

    report_number = models.CharField(max_length=15)
    comparison_type = models.CharField(
        max_length=20, choices=COMPARISON_CHOICES, default='period_over_period',
    )
    from_snapshot = models.ForeignKey(
        BenchmarkSnapshot, on_delete=models.PROTECT, related_name='compared_from',
    )
    to_snapshot = models.ForeignKey(
        BenchmarkSnapshot, on_delete=models.PROTECT, related_name='compared_to',
    )
    kwh_delta_pct = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    water_delta_pct = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    co2e_delta_pct = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    cost_delta_pct = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0'), validators=[SIGNED],
    )
    winner = models.CharField(max_length=120, blank=True)
    generated_at = models.DateTimeField(default=timezone.now)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='generated_benchmark_reports',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-generated_at']
        unique_together = ('tenant', 'report_number')

    def __str__(self):
        return f'{self.report_number} | {self.comparison_type}'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.report_number and self.tenant_id:
            last = (
                BenchmarkComparison.all_objects
                .filter(tenant_id=self.tenant_id, report_number__startswith='BCR-')
                .order_by('-report_number').first()
            )
            n = 1
            if last and last.report_number.startswith('BCR-'):
                try:
                    n = int(last.report_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.report_number = f'BCR-{n:05d}'
        super().save(*args, **kwargs)
