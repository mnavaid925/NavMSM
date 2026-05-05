"""Module 10 - Equipment & Asset Management (EAM).

Sub-modules:
    10.1  Asset Registry & Hierarchy        (AssetCategory, Asset,
                                             AssetSparePart, AssetMeterReading,
                                             AssetDocument)
    10.2  Preventive Maintenance (PM)       (MaintenancePlan, MaintenanceTask,
                                             PMSchedule, PMTaskCompletion)
    10.3  Predictive Maintenance            (ConditionMonitoringPoint,
                                             ConditionReading, FailurePrediction)
    10.4  Maintenance Work Orders           (MaintenanceWorkOrder, MWOLaborLog,
                                             MWOMaterialLog, DowntimeEvent)
    10.5  Tool & Die Management             (Tool, ToolUsageLog,
                                             ToolMaintenanceRecord,
                                             MoldCavityHistory)

Cross-module integration (additive, nullable FKs added in mes/qms):
    - apps.mes.AndonAlert.asset           -> eam.Asset
    - apps.mes.MESWorkOrder.tool          -> eam.Tool
    - apps.qms.MeasurementEquipment.asset -> eam.Asset
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel


# ============================================================================
# 10.1  ASSET REGISTRY & HIERARCHY
# ============================================================================

class AssetCategory(TenantAwareModel, TimeStampedModel):
    """Hierarchical asset taxonomy (e.g. Pumps -> Centrifugal -> Process)."""

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='children',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'name', 'parent')
        verbose_name_plural = 'Asset categories'

    def __str__(self):
        return self.name


class Asset(TenantAwareModel, TimeStampedModel):
    """Equipment master record. Parent-child supports e.g. CNC <- Spindle <- Bearing."""

    CRITICALITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    STATUS_CHOICES = [
        ('operational', 'Operational'),
        ('down', 'Down'),
        ('maintenance', 'Under Maintenance'),
        ('retired', 'Retired'),
    ]

    tag = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        AssetCategory, on_delete=models.PROTECT, related_name='assets',
        null=True, blank=True,
    )
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='children',
    )
    warehouse = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assets',
    )
    location_detail = models.CharField(
        max_length=255, blank=True,
        help_text='Free-text location within the warehouse (e.g. "Shop floor bay 3").',
    )
    manufacturer = models.CharField(max_length=200, blank=True)
    model_number = models.CharField(max_length=120, blank=True)
    serial_number = models.CharField(max_length=120, blank=True)
    installation_date = models.DateField(null=True, blank=True)
    commissioning_date = models.DateField(null=True, blank=True)
    criticality = models.CharField(max_length=10, choices=CRITICALITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='operational')
    purchase_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    current_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    warranty_expiry = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['tag']
        unique_together = ('tenant', 'tag')

    def __str__(self):
        return f'{self.tag} - {self.name}'

    def save(self, *args, **kwargs):
        if not self.tag and self.tenant_id:
            last = (
                Asset.all_objects
                .filter(tenant=self.tenant)
                .order_by('-id')
                .first()
            )
            seq = (last.id + 1) if last else 1
            self.tag = f'ASSET-{seq:05d}'
        super().save(*args, **kwargs)

    def is_active_status(self):
        return self.status not in ('retired',)

    def can_retire(self):
        return self.status != 'retired'


class AssetSparePart(TenantAwareModel, TimeStampedModel):
    """Through-table linking an asset to a spare-part product."""

    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name='spare_parts',
    )
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='asset_spare_for',
    )
    recommended_min_qty = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('1'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    quantity_on_hand = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Cached snapshot - real stock lives in inventory.',
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['asset', 'product']
        unique_together = ('asset', 'product')

    def __str__(self):
        return f'{self.asset.tag} :: {self.product.sku}'


class AssetMeterReading(TenantAwareModel, TimeStampedModel):
    """Append-only ledger of meter readings (hours run, cycles, mileage, kWh)."""

    METER_CHOICES = [
        ('hours', 'Operating Hours'),
        ('cycles', 'Cycles'),
        ('mileage', 'Mileage (km)'),
        ('kwh', 'Energy (kWh)'),
        ('other', 'Other'),
    ]

    asset = models.ForeignKey(
        Asset, on_delete=models.PROTECT, related_name='meter_readings',
    )
    meter_type = models.CharField(max_length=20, choices=METER_CHOICES, default='hours')
    reading_value = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0'))],
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='asset_meter_readings',
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['tenant', 'asset', 'meter_type', '-recorded_at']),
        ]

    def __str__(self):
        return f'{self.asset.tag} {self.meter_type}={self.reading_value}'


def _asset_doc_upload(instance, filename):
    return f'eam/assets/{instance.tenant_id}/{instance.asset_id}/{filename}'


class AssetDocument(TenantAwareModel, TimeStampedModel):
    DOC_CHOICES = [
        ('manual', 'Manual'),
        ('drawing', 'Drawing'),
        ('certificate', 'Certificate'),
        ('warranty', 'Warranty'),
        ('procedure', 'Procedure'),
        ('other', 'Other'),
    ]

    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name='documents',
    )
    name = models.CharField(max_length=200)
    doc_type = models.CharField(max_length=20, choices=DOC_CHOICES, default='manual')
    attachment = models.FileField(upload_to=_asset_doc_upload)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='asset_documents_uploaded',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['asset', '-created_at']

    def __str__(self):
        return f'{self.asset.tag} :: {self.name}'


# ============================================================================
# 10.2  PREVENTIVE MAINTENANCE (PM)
# ============================================================================

class MaintenancePlan(TenantAwareModel, TimeStampedModel):
    """Recurring PM plan attached to an asset (calendar/meter triggered)."""

    TRIGGER_CHOICES = [
        ('calendar', 'Calendar'),
        ('meter', 'Meter'),
        ('both', 'Calendar or Meter'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    asset = models.ForeignKey(
        Asset, on_delete=models.PROTECT, related_name='maintenance_plans',
    )
    trigger_type = models.CharField(
        max_length=10, choices=TRIGGER_CHOICES, default='calendar',
    )
    frequency_days = models.PositiveIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(3650)],
        help_text='Recurrence in days for calendar triggers.',
    )
    frequency_meter = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.0001'))],
        help_text='Recurrence in meter units (hours / cycles / km / kWh).',
    )
    meter_type = models.CharField(
        max_length=20, blank=True,
        help_text='Which meter to track (matches AssetMeterReading.meter_type).',
    )
    last_done_at = models.DateField(null=True, blank=True)
    last_done_meter = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0'))],
    )
    next_due_at = models.DateField(null=True, blank=True)
    next_due_meter = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0'))],
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_pm_plans',
    )

    class Meta:
        ordering = ['asset', 'name']
        unique_together = ('tenant', 'asset', 'name')

    def __str__(self):
        return f'{self.asset.tag} :: {self.name}'


class MaintenanceTask(TenantAwareModel, TimeStampedModel):
    """A checklist item template inside a MaintenancePlan."""

    plan = models.ForeignKey(
        MaintenancePlan, on_delete=models.CASCADE, related_name='tasks',
    )
    sequence = models.PositiveIntegerField(default=10)
    description = models.CharField(max_length=255)
    instructions = models.TextField(blank=True)
    expected_minutes = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    is_critical = models.BooleanField(default=False)

    class Meta:
        ordering = ['plan', 'sequence']
        unique_together = ('plan', 'sequence')

    def __str__(self):
        return f'{self.plan.name} S{self.sequence}'


class PMSchedule(TenantAwareModel, TimeStampedModel):
    """A specific upcoming PM event materialised from a MaintenancePlan."""

    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('skipped', 'Skipped'),
        ('overdue', 'Overdue'),
    ]

    schedule_number = models.CharField(max_length=20)
    plan = models.ForeignKey(
        MaintenancePlan, on_delete=models.PROTECT, related_name='schedules',
    )
    scheduled_date = models.DateField()
    scheduled_meter = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0'))],
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pm_schedules_assigned',
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pm_schedules_completed',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['scheduled_date', 'plan']
        unique_together = ('tenant', 'schedule_number')
        indexes = [
            models.Index(fields=['tenant', 'status', 'scheduled_date']),
            models.Index(fields=['tenant', 'plan', 'scheduled_date']),
        ]

    def __str__(self):
        return self.schedule_number

    def save(self, *args, **kwargs):
        if not self.schedule_number and self.tenant_id:
            last = (
                PMSchedule.all_objects
                .filter(tenant=self.tenant)
                .order_by('-id')
                .first()
            )
            seq = (last.id + 1) if last else 1
            self.schedule_number = f'PMS-{seq:05d}'
        super().save(*args, **kwargs)

    def is_actionable(self):
        return self.status in ('scheduled', 'in_progress', 'overdue')


class PMTaskCompletion(TenantAwareModel, TimeStampedModel):
    """One operator-recorded result against one PMSchedule task."""

    RESULT_CHOICES = [
        ('pass', 'Pass'),
        ('fail', 'Fail'),
        ('na', 'Not Applicable'),
    ]

    pm_schedule = models.ForeignKey(
        PMSchedule, on_delete=models.PROTECT, related_name='task_completions',
    )
    task = models.ForeignKey(
        MaintenanceTask, on_delete=models.PROTECT, related_name='completions',
    )
    result = models.CharField(max_length=10, choices=RESULT_CHOICES)
    comments = models.TextField(blank=True)
    completed_at = models.DateTimeField(default=timezone.now)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pm_task_completions',
    )

    class Meta:
        ordering = ['pm_schedule', 'task__sequence']
        unique_together = ('pm_schedule', 'task')

    def __str__(self):
        return f'{self.pm_schedule.schedule_number} :: {self.task} = {self.result}'


# ============================================================================
# 10.3  PREDICTIVE MAINTENANCE
# ============================================================================

class ConditionMonitoringPoint(TenantAwareModel, TimeStampedModel):
    """A measurement location on an asset (sensor, inspection point, sample tap)."""

    PARAMETER_CHOICES = [
        ('vibration', 'Vibration'),
        ('temperature', 'Temperature'),
        ('pressure', 'Pressure'),
        ('current', 'Current'),
        ('oil_quality', 'Oil Quality'),
        ('noise', 'Noise'),
        ('other', 'Other'),
    ]

    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name='monitoring_points',
    )
    name = models.CharField(max_length=200)
    parameter = models.CharField(max_length=20, choices=PARAMETER_CHOICES, default='vibration')
    unit = models.CharField(max_length=20, blank=True)
    low_alarm = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    high_alarm = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['asset', 'name']
        unique_together = ('tenant', 'asset', 'name')

    def __str__(self):
        return f'{self.asset.tag} :: {self.name}'


class ConditionReading(TenantAwareModel, TimeStampedModel):
    """Append-only sensor reading. Auto-classified normal/warning/critical."""

    STATUS_CHOICES = [
        ('normal', 'Normal'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]

    point = models.ForeignKey(
        ConditionMonitoringPoint, on_delete=models.PROTECT,
        related_name='readings',
    )
    reading_value = models.DecimalField(max_digits=14, decimal_places=4)
    recorded_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='condition_readings',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='normal')
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['tenant', 'point', '-recorded_at']),
            models.Index(fields=['tenant', 'status', '-recorded_at']),
        ]

    def __str__(self):
        return f'{self.point} = {self.reading_value} ({self.status})'


class FailurePrediction(TenantAwareModel, TimeStampedModel):
    """Heuristic failure prediction. v1 uses alarm-band rules only."""

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('investigating', 'Investigating'),
        ('resolved', 'Resolved'),
        ('false_positive', 'False Positive'),
    ]

    asset = models.ForeignKey(
        Asset, on_delete=models.PROTECT, related_name='failure_predictions',
    )
    triggered_by_reading = models.ForeignKey(
        ConditionReading, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='triggered_predictions',
    )
    predicted_failure_date = models.DateField(null=True, blank=True)
    confidence_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    summary = models.CharField(max_length=255)
    recommended_action = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='resolved_failure_predictions',
    )
    resolution_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'asset', 'status']),
            models.Index(fields=['tenant', 'status', '-created_at']),
        ]

    def __str__(self):
        return f'{self.asset.tag} :: {self.summary} ({self.status})'

    def is_open(self):
        return self.status in ('open', 'investigating')


# ============================================================================
# 10.4  MAINTENANCE WORK ORDERS
# ============================================================================

class MaintenanceWorkOrder(TenantAwareModel, TimeStampedModel):
    """A maintenance work order (breakdown / preventive / corrective / etc.)."""

    WO_TYPE_CHOICES = [
        ('breakdown', 'Breakdown'),
        ('preventive', 'Preventive'),
        ('corrective', 'Corrective'),
        ('predictive', 'Predictive'),
        ('inspection', 'Inspection'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    mwo_number = models.CharField(max_length=20)
    asset = models.ForeignKey(
        Asset, on_delete=models.PROTECT, related_name='work_orders',
    )
    wo_type = models.CharField(max_length=20, choices=WO_TYPE_CHOICES, default='corrective')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    title = models.CharField(max_length=255)
    problem_description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reported_mwos',
    )
    reported_at = models.DateTimeField(default=timezone.now)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_mwos',
    )
    scheduled_start = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='completed_mwos',
    )

    downtime_minutes = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Computed denorm from related DowntimeEvent rows.',
    )
    failure_code = models.CharField(max_length=60, blank=True)
    root_cause = models.TextField(blank=True)
    resolution_notes = models.TextField(blank=True)

    # Source FKs (all nullable - work orders may originate from many places).
    source_pm_schedule = models.ForeignKey(
        PMSchedule, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='spawned_work_orders',
    )
    source_failure_prediction = models.ForeignKey(
        FailurePrediction, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='spawned_work_orders',
    )
    source_andon = models.ForeignKey(
        'mes.AndonAlert', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='spawned_eam_work_orders',
    )

    class Meta:
        ordering = ['-reported_at']
        unique_together = ('tenant', 'mwo_number')
        indexes = [
            models.Index(fields=['tenant', 'status', '-reported_at']),
            models.Index(fields=['tenant', 'asset', 'status']),
        ]
        verbose_name = 'Maintenance Work Order'

    def __str__(self):
        return self.mwo_number

    def save(self, *args, **kwargs):
        if not self.mwo_number and self.tenant_id:
            last = (
                MaintenanceWorkOrder.all_objects
                .filter(tenant=self.tenant)
                .order_by('-id')
                .first()
            )
            seq = (last.id + 1) if last else 1
            self.mwo_number = f'MWO-{seq:05d}'
        super().save(*args, **kwargs)

    def is_editable(self):
        return self.status in ('draft', 'scheduled', 'on_hold')

    def can_start(self):
        return self.status in ('draft', 'scheduled', 'on_hold')

    def can_hold(self):
        return self.status == 'in_progress'

    def can_complete(self):
        return self.status == 'in_progress'

    def can_cancel(self):
        return self.status not in ('completed', 'cancelled')


class MWOLaborLog(TenantAwareModel, TimeStampedModel):
    """Append-only labor log for a maintenance work order."""

    mwo = models.ForeignKey(
        MaintenanceWorkOrder, on_delete=models.PROTECT, related_name='labor_logs',
    )
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='mwo_labor_logs',
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    minutes = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    total_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['mwo', '-started_at']

    def __str__(self):
        return f'{self.mwo.mwo_number} :: {self.technician} {self.minutes}m'

    def save(self, *args, **kwargs):
        if self.started_at and self.ended_at:
            delta = (self.ended_at - self.started_at).total_seconds() / 60.0
            self.minutes = Decimal(f'{max(delta, 0.0):.2f}')
        rate_per_min = (self.hourly_rate or Decimal('0')) / Decimal('60')
        self.total_cost = ((self.minutes or Decimal('0')) * rate_per_min).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)


class MWOMaterialLog(TenantAwareModel, TimeStampedModel):
    """Append-only material consumption log for a maintenance work order."""

    mwo = models.ForeignKey(
        MaintenanceWorkOrder, on_delete=models.PROTECT, related_name='material_logs',
    )
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='mwo_material_logs',
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    unit_of_measure = models.CharField(max_length=20, default='EA')
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    total_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    stock_movement = models.ForeignKey(
        'inventory.StockMovement', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='mwo_material_logs',
    )
    used_at = models.DateTimeField(default=timezone.now)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['mwo', '-used_at']

    def __str__(self):
        return f'{self.mwo.mwo_number} :: {self.product.sku} x {self.quantity}'

    def save(self, *args, **kwargs):
        gross = (self.quantity or Decimal('0')) * (self.unit_cost or Decimal('0'))
        self.total_cost = gross.quantize(Decimal('0.01'))
        super().save(*args, **kwargs)


class DowntimeEvent(TenantAwareModel, TimeStampedModel):
    """Append-only downtime event for an asset (planned or unplanned)."""

    DOWNTIME_TYPE_CHOICES = [
        ('planned', 'Planned'),
        ('unplanned', 'Unplanned'),
    ]

    asset = models.ForeignKey(
        Asset, on_delete=models.PROTECT, related_name='downtime_events',
    )
    mwo = models.ForeignKey(
        MaintenanceWorkOrder, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='downtime_events',
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    minutes = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    downtime_type = models.CharField(
        max_length=10, choices=DOWNTIME_TYPE_CHOICES, default='unplanned',
    )
    reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['tenant', 'asset', '-started_at']),
        ]

    def __str__(self):
        return f'{self.asset.tag} {self.downtime_type} {self.minutes}m'

    def save(self, *args, **kwargs):
        if self.started_at and self.ended_at:
            delta = (self.ended_at - self.started_at).total_seconds() / 60.0
            self.minutes = Decimal(f'{max(delta, 0.0):.2f}')
        super().save(*args, **kwargs)


# ============================================================================
# 10.5  TOOL & DIE MANAGEMENT
# ============================================================================

class Tool(TenantAwareModel, TimeStampedModel):
    """Production tooling: molds, dies, jigs, fixtures, cutting tools, gauges."""

    TOOL_TYPE_CHOICES = [
        ('mold', 'Mold'),
        ('die', 'Die'),
        ('jig', 'Jig'),
        ('fixture', 'Fixture'),
        ('cutting_tool', 'Cutting Tool'),
        ('gauge', 'Gauge'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('in_use', 'In Use'),
        ('maintenance', 'Maintenance'),
        ('retired', 'Retired'),
    ]

    tool_id = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    tool_type = models.CharField(max_length=20, choices=TOOL_TYPE_CHOICES, default='cutting_tool')
    category = models.CharField(max_length=120, blank=True)
    location = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    purchase_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    expected_life_cycles = models.PositiveIntegerField(default=0)
    current_cycles = models.PositiveIntegerField(default=0)
    expected_life_hours = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    current_hours = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    last_sharpened_at = models.DateField(null=True, blank=True)
    next_sharpen_due = models.DateField(null=True, blank=True)
    cavity_count = models.PositiveIntegerField(
        default=0,
        help_text='For molds: number of cavities. 0 for non-molds.',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['tool_id']
        unique_together = ('tenant', 'tool_id')

    def __str__(self):
        return f'{self.tool_id} - {self.name}'

    def save(self, *args, **kwargs):
        if not self.tool_id and self.tenant_id:
            last = (
                Tool.all_objects
                .filter(tenant=self.tenant)
                .order_by('-id')
                .first()
            )
            seq = (last.id + 1) if last else 1
            self.tool_id = f'TOOL-{seq:05d}'
        super().save(*args, **kwargs)

    def cycles_remaining(self):
        if not self.expected_life_cycles:
            return None
        return max(self.expected_life_cycles - self.current_cycles, 0)

    def hours_remaining(self):
        if not self.expected_life_hours:
            return None
        return max(self.expected_life_hours - self.current_hours, Decimal('0'))


class ToolUsageLog(TenantAwareModel, TimeStampedModel):
    """Append-only usage log. Auto-emitted from mes.ProductionReport.post_save."""

    tool = models.ForeignKey(
        Tool, on_delete=models.PROTECT, related_name='usage_logs',
    )
    mes_work_order = models.ForeignKey(
        'mes.MESWorkOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='tool_usage_logs',
    )
    used_at = models.DateTimeField(default=timezone.now)
    cycles_added = models.PositiveIntegerField(default=0)
    hours_added = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='tool_usage_logs',
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-used_at']
        indexes = [
            models.Index(fields=['tenant', 'tool', '-used_at']),
        ]

    def __str__(self):
        return f'{self.tool.tool_id} +{self.cycles_added}c +{self.hours_added}h'


def _tool_maint_upload(instance, filename):
    return f'eam/tools/{instance.tenant_id}/{instance.tool_id}/{filename}'


class ToolMaintenanceRecord(TenantAwareModel, TimeStampedModel):
    """Append-only maintenance log for a tool (sharpening, calibration, repair)."""

    RECORD_TYPE_CHOICES = [
        ('sharpening', 'Sharpening'),
        ('cleaning', 'Cleaning'),
        ('repair', 'Repair'),
        ('calibration', 'Calibration'),
        ('inspection', 'Inspection'),
    ]

    tool = models.ForeignKey(
        Tool, on_delete=models.PROTECT, related_name='maintenance_records',
    )
    record_type = models.CharField(
        max_length=20, choices=RECORD_TYPE_CHOICES, default='sharpening',
    )
    performed_at = models.DateField(default=timezone.now)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='tool_maintenance_records',
    )
    cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    notes = models.TextField(blank=True)
    attachment = models.FileField(
        upload_to=_tool_maint_upload, blank=True, null=True,
    )

    class Meta:
        ordering = ['-performed_at']

    def __str__(self):
        return f'{self.tool.tool_id} {self.record_type} @ {self.performed_at}'


class MoldCavityHistory(TenantAwareModel, TimeStampedModel):
    """Per-cavity history for mold-type tools."""

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('blocked', 'Blocked'),
        ('repaired', 'Repaired'),
    ]

    tool = models.ForeignKey(
        Tool, on_delete=models.CASCADE, related_name='cavity_histories',
    )
    cavity_number = models.PositiveIntegerField()
    cycles = models.PositiveIntegerField(default=0)
    last_inspected_at = models.DateField(null=True, blank=True)
    defect_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['tool', 'cavity_number']
        unique_together = ('tool', 'cavity_number')
        verbose_name_plural = 'Mold cavity histories'

    def __str__(self):
        return f'{self.tool.tool_id} :: cavity {self.cavity_number}'
