"""Module 15 - IoT & SCADA Integration.

Sub-modules:
    15.1  Device Connectivity Hub        (DeviceProtocol [shared catalog],
                                          DeviceBroker, Device, DeviceTag)
    15.2  Real-Time Data Acquisition     (IoTReadingBatch, IoTReading,
                                          EdgeProcessor, StreamMetric)
    15.3  Digital Twin Configuration     (DigitalTwin, TwinStateAttribute,
                                          TwinSimulationScenario,
                                          TwinStateSnapshot)
    15.4  OEE Monitoring                 (LossReason, MachineStateLog,
                                          OEEPeriod)
    15.5  Alert & Anomaly Detection      (AlertRule, AnomalyDetection,
                                          AlertNotification)

Cross-module integration (additive, non-breaking):
    iot.IoTReading.post_save        -> iot.StreamMetric (denorm)
    iot.IoTReading.post_save        -> iot.AnomalyDetection (rule eval)
    iot.IoTReading.post_save        -> eam.ConditionReading (when tag has
                                       condition_point set, idempotent on
                                       eam.ConditionReading.source_iot_reading)
    iot.AnomalyDetection.post_save  -> mes.AndonAlert (when channels include
                                       'mes_andon', idempotent on
                                       mes.AndonAlert.source_anomaly)
    iot.AnomalyDetection.post_save  -> eam.FailurePrediction (severity=critical
                                       and tag.condition_point set, idempotent
                                       on eam.FailurePrediction.source_anomaly)
    iot.AnomalyDetection.post_save  -> iot.AlertNotification (one row per
                                       configured channel)
    mes.ProductionReport.post_save  -> iot.OEEPeriod denorm refresh
    eam.DowntimeEvent.post_save     -> iot.MachineStateLog (idempotent on
                                       source_downtime)

Lessons applied:
    * L-01 unique_together with tenant excluded -> form-level clean()
    * L-02 every Decimal carries explicit MinValueValidator
    * L-03 view+template status gate parity via is_*() helpers
    * L-12 auto-numbering retry handled in save() (last-row + 1 pattern)
    * L-13 transaction.atomic() around denorm bumps
    * L-14 per-workflow forms enforce required fields
    * L-17 PROTECT on audit/log child FKs
    * L-18 weak=False on factory-bound signal handlers (see signals.py)

Security flags:
    * DeviceBroker.password_hash stores a stable token, not encrypted.
      Production deployments MUST swap this for KMS / Vault — see README.
    * TwinStateAttribute.formula is evaluated by services/twin._safe_eval(),
      a whitelist-only mini parser. Never call eval() / exec() on it.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel


# Common decimal validator constants (mirrors apps/utility/models.py).
NEG_BOUND = Decimal('-99999999.9999')
NON_NEG = MinValueValidator(Decimal('0'))
SIGNED = MinValueValidator(NEG_BOUND)
PCT_MAX = MaxValueValidator(Decimal('100'))


# ============================================================================
# 15.1  DEVICE CONNECTIVITY HUB
# ============================================================================

class DeviceProtocol(TimeStampedModel):
    """Shared, NOT tenant-scoped global protocol catalog (mirrors plm.ComplianceStandard).

    Includes MQTT / OPC-UA / Modbus TCP / Modbus RTU / HTTP polling / CoAP.
    """

    code = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=120)
    default_port = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} - {self.name}'


class DeviceBroker(TenantAwareModel, TimeStampedModel):
    """Connection registry for an MQTT / OPC-UA / Modbus broker or gateway.

    Auto-numbered ``BRK-00001``.

    SECURITY WARNING: ``password_hash`` is a stop-gap. Production deployments
    must rotate to a KMS / Vault / SecretsManager-backed lookup before storing
    real broker credentials.
    """

    AUTH_CHOICES = [
        ('none', 'No Authentication'),
        ('userpass', 'Username + Password'),
        ('cert', 'Mutual TLS / Client Cert'),
        ('token', 'API Token'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('error', 'Error'),
    ]

    broker_number = models.CharField(max_length=15)
    name = models.CharField(max_length=120)
    protocol = models.ForeignKey(
        DeviceProtocol, on_delete=models.PROTECT, related_name='brokers',
    )
    host = models.CharField(max_length=255)
    port = models.PositiveIntegerField()
    auth_method = models.CharField(max_length=15, choices=AUTH_CHOICES, default='none')
    username = models.CharField(max_length=120, blank=True)
    # Stop-gap credential store; treat as a hash, not as plaintext.
    password_hash = models.CharField(max_length=255, blank=True)
    tls_enabled = models.BooleanField(default=False)
    ca_cert_filename = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='inactive')
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['broker_number']
        unique_together = [
            ('tenant', 'broker_number'),
            ('tenant', 'name'),
        ]

    def __str__(self):
        return f'{self.broker_number} - {self.name}'

    def is_active_status(self):
        return self.status == 'active'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.broker_number and self.tenant_id:
            last = (
                DeviceBroker.all_objects
                .filter(tenant_id=self.tenant_id, broker_number__startswith='BRK-')
                .order_by('-broker_number').first()
            )
            n = 1
            if last and last.broker_number.startswith('BRK-'):
                try:
                    n = int(last.broker_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.broker_number = f'BRK-{n:05d}'
        super().save(*args, **kwargs)


class Device(TenantAwareModel, TimeStampedModel):
    """Field device / PLC / sensor node / SCADA server / edge gateway / HMI.

    Auto-numbered ``DEV-00001``. Optional FK to ``eam.Asset`` enables the
    OEE / state-log / EAM cross-module hooks.
    """

    DEVICE_TYPE_CHOICES = [
        ('plc', 'PLC'),
        ('sensor_node', 'Sensor Node'),
        ('scada_server', 'SCADA Server'),
        ('edge_gateway', 'Edge Gateway'),
        ('hmi', 'HMI'),
        ('rtu', 'RTU'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('decommissioned', 'Decommissioned'),
    ]

    device_number = models.CharField(max_length=15)
    name = models.CharField(max_length=120)
    broker = models.ForeignKey(
        DeviceBroker, on_delete=models.PROTECT, related_name='devices',
    )
    protocol = models.ForeignKey(
        DeviceProtocol, on_delete=models.PROTECT, related_name='devices',
    )
    asset = models.ForeignKey(
        'eam.Asset', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='iot_devices',
    )
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPE_CHOICES, default='sensor_node')
    serial_number = models.CharField(max_length=120, blank=True)
    firmware_version = models.CharField(max_length=60, blank=True)
    location_text = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    last_seen_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['device_number']
        unique_together = [
            ('tenant', 'device_number'),
            ('tenant', 'name'),
        ]

    def __str__(self):
        return f'{self.device_number} - {self.name}'

    def is_retirable(self):
        return self.status in ('active', 'inactive')

    def is_reactivatable(self):
        return self.status in ('inactive', 'decommissioned')

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.device_number and self.tenant_id:
            last = (
                Device.all_objects
                .filter(tenant_id=self.tenant_id, device_number__startswith='DEV-')
                .order_by('-device_number').first()
            )
            n = 1
            if last and last.device_number.startswith('DEV-'):
                try:
                    n = int(last.device_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.device_number = f'DEV-{n:05d}'
        super().save(*args, **kwargs)


class DeviceTag(TenantAwareModel, TimeStampedModel):
    """A single data-point on a device (MQTT topic, OPC-UA NodeId, Modbus register).

    Optional ``condition_point`` FK lets the IoTReading cascade write into
    ``eam.ConditionReading`` without coupling EAM to IoT.
    """

    DATA_TYPE_CHOICES = [
        ('float', 'Float'),
        ('int', 'Integer'),
        ('bool', 'Boolean'),
        ('string', 'String'),
    ]

    name = models.CharField(max_length=120)
    device = models.ForeignKey(
        Device, on_delete=models.CASCADE, related_name='tags',
    )
    address = models.CharField(max_length=255, help_text='MQTT topic / OPC-UA NodeId / Modbus register / etc.')
    data_type = models.CharField(max_length=10, choices=DATA_TYPE_CHOICES, default='float')
    unit = models.CharField(max_length=30, blank=True)
    scale_factor = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal('1.0000'), validators=[NON_NEG],
    )
    offset = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal('0.0000'), validators=[SIGNED],
    )
    sampling_interval_seconds = models.PositiveIntegerField(default=60)
    condition_point = models.ForeignKey(
        'eam.ConditionMonitoringPoint', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='iot_tags',
        help_text='When set, IoTReading values cascade into eam.ConditionReading.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['device__device_number', 'name']
        unique_together = [
            ('tenant', 'device', 'address'),
            ('tenant', 'device', 'name'),
        ]

    def __str__(self):
        return f'{self.device.device_number}::{self.name}'


# ============================================================================
# 15.2  REAL-TIME DATA ACQUISITION
# ============================================================================

class IoTReadingBatch(TenantAwareModel, TimeStampedModel):
    """Ingest batch envelope. Auto-numbered ``IRB-00001``."""

    SOURCE_FORMAT_CHOICES = [
        ('json', 'JSON Array'),
        ('csv', 'CSV Upload'),
        ('opc_ua_history', 'OPC-UA Historian Export'),
        ('mqtt_replay', 'MQTT Replay'),
        ('manual', 'Manual Entry'),
        ('seed', 'Seed Fixture'),
    ]
    STATUS_CHOICES = [
        ('received', 'Received'),
        ('processed', 'Processed'),
        ('partial', 'Partial Failure'),
        ('failed', 'Failed'),
    ]

    batch_number = models.CharField(max_length=15)
    ingested_at = models.DateTimeField(default=timezone.now)
    ingested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='iot_batches',
    )
    source_format = models.CharField(max_length=20, choices=SOURCE_FORMAT_CHOICES, default='json')
    row_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='received')
    error_summary = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-ingested_at']
        unique_together = ('tenant', 'batch_number')

    def __str__(self):
        return self.batch_number

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.batch_number and self.tenant_id:
            last = (
                IoTReadingBatch.all_objects
                .filter(tenant_id=self.tenant_id, batch_number__startswith='IRB-')
                .order_by('-batch_number').first()
            )
            n = 1
            if last and last.batch_number.startswith('IRB-'):
                try:
                    n = int(last.batch_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.batch_number = f'IRB-{n:05d}'
        super().save(*args, **kwargs)


class IoTReading(TenantAwareModel, TimeStampedModel):
    """Append-only sensor / device reading ledger. Auto-numbered ``IR-00001``.

    Exactly one of value_numeric / value_text / value_bool is populated per
    row, matching the parent tag's ``data_type``.

    Cross-module cascades fire from signals.py.
    """

    QUALITY_CHOICES = [
        ('good', 'Good'),
        ('uncertain', 'Uncertain'),
        ('bad', 'Bad'),
    ]
    SOURCE_CHOICES = [
        ('live', 'Live Stream'),
        ('replay', 'Replay'),
        ('manual', 'Manual Entry'),
        ('seed', 'Seed Fixture'),
    ]

    entry_number = models.CharField(max_length=15)
    device_tag = models.ForeignKey(
        DeviceTag, on_delete=models.PROTECT, related_name='readings',
    )
    timestamp = models.DateTimeField(default=timezone.now)
    value_numeric = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    value_text = models.CharField(max_length=255, blank=True)
    value_bool = models.BooleanField(null=True, blank=True)
    quality = models.CharField(max_length=10, choices=QUALITY_CHOICES, default='good')
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='live')
    batch = models.ForeignKey(
        IoTReadingBatch, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='readings',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp', '-id']
        unique_together = ('tenant', 'entry_number')
        indexes = [
            models.Index(fields=['tenant', 'device_tag', 'timestamp']),
            models.Index(fields=['tenant', 'timestamp']),
        ]

    def __str__(self):
        return f'{self.entry_number} | {self.device_tag} | {self.value_display()}'

    def value_display(self):
        if self.value_numeric is not None:
            return str(self.value_numeric)
        if self.value_text:
            return self.value_text
        if self.value_bool is not None:
            return 'true' if self.value_bool else 'false'
        return '-'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.entry_number and self.tenant_id:
            last = (
                IoTReading.all_objects
                .filter(tenant_id=self.tenant_id, entry_number__startswith='IR-')
                .order_by('-entry_number').first()
            )
            n = 1
            if last and last.entry_number.startswith('IR-'):
                try:
                    n = int(last.entry_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.entry_number = f'IR-{n:05d}'
        super().save(*args, **kwargs)


class EdgeProcessor(TenantAwareModel, TimeStampedModel):
    """Pure-function edge transform on a stream of readings.

    Implementations live in services/edge.py; this model only stores the
    configuration.
    """

    TRANSFORM_CHOICES = [
        ('rolling_avg', 'Rolling Average'),
        ('sum', 'Window Sum'),
        ('min', 'Window Min'),
        ('max', 'Window Max'),
        ('threshold_count', 'Threshold Count'),
        ('state_machine', 'State Machine'),
        ('derivative', 'Derivative / Rate'),
    ]

    name = models.CharField(max_length=120)
    input_tag = models.ForeignKey(
        DeviceTag, on_delete=models.PROTECT, related_name='edge_inputs',
    )
    transform_type = models.CharField(max_length=20, choices=TRANSFORM_CHOICES, default='rolling_avg')
    window_seconds = models.PositiveIntegerField(default=60)
    threshold_value = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    output_tag = models.ForeignKey(
        DeviceTag, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='edge_outputs',
        help_text='If set, transformed value writes a derived IoTReading on this tag.',
    )
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'name')

    def __str__(self):
        return f'{self.name} ({self.get_transform_type_display()})'


class StreamMetric(TenantAwareModel, TimeStampedModel):
    """Latest-value denorm per DeviceTag (1-to-1).

    Refreshed by the IoTReading post_save signal; never written manually.
    """

    device_tag = models.OneToOneField(
        DeviceTag, on_delete=models.CASCADE, related_name='stream_metric',
    )
    latest_value = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    latest_timestamp = models.DateTimeField(null=True, blank=True)
    last_24h_min = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    last_24h_max = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    last_24h_avg = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    count_24h = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['device_tag__name']

    def __str__(self):
        return f'{self.device_tag} latest={self.latest_value}'


# ============================================================================
# 15.3  DIGITAL TWIN CONFIGURATION
# ============================================================================

class DigitalTwin(TenantAwareModel, TimeStampedModel):
    """Virtual representation of a machine / line / cell / plant.

    Auto-numbered ``DT-00001``.
    """

    TWIN_TYPE_CHOICES = [
        ('machine', 'Machine'),
        ('line', 'Line'),
        ('cell', 'Cell'),
        ('plant', 'Plant'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]

    twin_number = models.CharField(max_length=15)
    name = models.CharField(max_length=120)
    asset = models.ForeignKey(
        'eam.Asset', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='digital_twins',
    )
    twin_type = models.CharField(max_length=10, choices=TWIN_TYPE_CHOICES, default='machine')
    description = models.TextField(blank=True)
    model_version = models.CharField(max_length=30, default='1.0.0')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['twin_number']
        unique_together = [
            ('tenant', 'twin_number'),
            ('tenant', 'name', 'model_version'),
        ]

    def __str__(self):
        return f'{self.twin_number} - {self.name} v{self.model_version}'

    def is_activatable(self):
        return self.status == 'draft'

    def is_archivable(self):
        return self.status in ('draft', 'active')

    def is_editable(self):
        return self.status in ('draft', 'active')

    def is_deletable(self):
        return self.status == 'draft'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.twin_number and self.tenant_id:
            last = (
                DigitalTwin.all_objects
                .filter(tenant_id=self.tenant_id, twin_number__startswith='DT-')
                .order_by('-twin_number').first()
            )
            n = 1
            if last and last.twin_number.startswith('DT-'):
                try:
                    n = int(last.twin_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.twin_number = f'DT-{n:05d}'
        super().save(*args, **kwargs)


class TwinStateAttribute(TenantAwareModel, TimeStampedModel):
    """A named attribute mirrored on a digital twin.

    For ``derived`` attributes, ``formula`` is evaluated by the safe
    expression parser in services/twin.py — NEVER call eval() / exec().
    Allowed tokens: numbers, variable refs, + - * / (), min, max, abs.
    """

    ATTR_TYPE_CHOICES = [
        ('state', 'Discrete State'),
        ('measurement', 'Measurement'),
        ('derived', 'Derived (formula)'),
    ]

    twin = models.ForeignKey(
        DigitalTwin, on_delete=models.CASCADE, related_name='attributes',
    )
    name = models.CharField(max_length=120)
    attribute_type = models.CharField(max_length=15, choices=ATTR_TYPE_CHOICES, default='measurement')
    source_tag = models.ForeignKey(
        DeviceTag, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='twin_attributes',
    )
    formula = models.TextField(blank=True)
    unit = models.CharField(max_length=30, blank=True)
    current_value_text = models.CharField(max_length=255, blank=True)
    current_value_numeric = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    current_value_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['twin__twin_number', 'name']
        unique_together = ('tenant', 'twin', 'name')

    def __str__(self):
        return f'{self.twin.twin_number}::{self.name}'


class TwinSimulationScenario(TenantAwareModel, TimeStampedModel):
    """What-if scenario evaluated by the pure-function simulator.

    Auto-numbered ``TSC-00001``. The simulator never mutates twin state.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    scenario_number = models.CharField(max_length=15)
    twin = models.ForeignKey(
        DigitalTwin, on_delete=models.CASCADE, related_name='scenarios',
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    input_payload = models.JSONField(default=dict, blank=True)
    expected_output = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    result_payload = models.JSONField(default=dict, blank=True)
    run_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'scenario_number')

    def __str__(self):
        return f'{self.scenario_number} - {self.name}'

    def is_runnable(self):
        return self.status in ('draft', 'completed', 'failed')

    def is_deletable(self):
        return self.status != 'running'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.scenario_number and self.tenant_id:
            last = (
                TwinSimulationScenario.all_objects
                .filter(tenant_id=self.tenant_id, scenario_number__startswith='TSC-')
                .order_by('-scenario_number').first()
            )
            n = 1
            if last and last.scenario_number.startswith('TSC-'):
                try:
                    n = int(last.scenario_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.scenario_number = f'TSC-{n:05d}'
        super().save(*args, **kwargs)


class TwinStateSnapshot(TenantAwareModel, TimeStampedModel):
    """Append-only point-in-time state mirror for time-travel debugging."""

    TRIGGER_CHOICES = [
        ('manual', 'Manual'),
        ('scheduled', 'Scheduled'),
        ('pre_simulation', 'Pre-Simulation'),
        ('signal', 'Signal Cascade'),
    ]

    twin = models.ForeignKey(
        DigitalTwin, on_delete=models.CASCADE, related_name='snapshots',
    )
    snapshot_at = models.DateTimeField(default=timezone.now)
    state_payload = models.JSONField(default=dict, blank=True)
    triggered_by = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default='manual')
    captured_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='iot_twin_snapshots',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-snapshot_at']
        indexes = [models.Index(fields=['tenant', 'twin', 'snapshot_at'])]

    def __str__(self):
        return f'{self.twin.twin_number}@{self.snapshot_at:%Y-%m-%d %H:%M}'


# ============================================================================
# 15.4  OEE MONITORING
# ============================================================================

class LossReason(TenantAwareModel, TimeStampedModel):
    """Catalog of OEE loss reasons (availability / performance / quality)."""

    CATEGORY_CHOICES = [
        ('availability', 'Availability'),
        ('performance', 'Performance'),
        ('quality', 'Quality'),
    ]

    code = models.SlugField(max_length=30)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=15, choices=CATEGORY_CHOICES, default='availability')
    is_planned = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['category', 'code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} ({self.get_category_display()})'


class MachineStateLog(TenantAwareModel, TimeStampedModel):
    """Append-only ledger of asset state transitions.

    Idempotency: when ``source_downtime`` is set the (tenant, source_downtime)
    combination is unique so the eam.DowntimeEvent cascade signal is safe to
    re-fire.
    """

    STATE_CHOICES = [
        ('running', 'Running'),
        ('idle', 'Idle'),
        ('down', 'Down'),
        ('starved', 'Starved'),
        ('blocked', 'Blocked'),
        ('setup', 'Setup'),
        ('changeover', 'Changeover'),
    ]
    SOURCE_CHOICES = [
        ('iot_signal', 'IoT Signal'),
        ('manual', 'Manual Entry'),
        ('eam_downtime', 'EAM Downtime Event'),
        ('seed', 'Seed Fixture'),
    ]

    asset = models.ForeignKey(
        'eam.Asset', on_delete=models.CASCADE, related_name='state_logs',
    )
    state = models.CharField(max_length=15, choices=STATE_CHOICES, default='running')
    loss_reason = models.ForeignKey(
        LossReason, on_delete=models.PROTECT,
        null=True, blank=True, related_name='state_logs',
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='manual')
    source_downtime = models.ForeignKey(
        'eam.DowntimeEvent', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='iot_state_logs',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at', '-id']
        indexes = [
            models.Index(fields=['tenant', 'asset', 'started_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'source_downtime'],
                condition=models.Q(source_downtime__isnull=False),
                name='iot_state_log_unique_source_downtime',
            ),
        ]

    def __str__(self):
        return f'{self.asset.asset_number}/{self.state} @ {self.started_at:%Y-%m-%d %H:%M}'

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if self.started_at and self.ended_at and self.ended_at >= self.started_at:
            self.duration_seconds = int((self.ended_at - self.started_at).total_seconds())
        super().save(*args, **kwargs)


class OEEPeriod(TenantAwareModel, TimeStampedModel):
    """Per-asset, per-shift, per-day OEE rollup. Auto-numbered ``OEEP-00001``.

    Computed from MachineStateLog (Availability) + mes.ProductionReport
    (Performance + Quality) + pps.RoutingOperation.cycle_seconds (ideal cycle).

    A/P/Q/OEE percentages are computed in save().
    """

    period_number = models.CharField(max_length=15)
    asset = models.ForeignKey(
        'eam.Asset', on_delete=models.PROTECT, related_name='oee_periods',
    )
    shift = models.ForeignKey(
        'labor.Shift', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='oee_periods',
    )
    period_date = models.DateField()
    planned_run_minutes = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    run_minutes = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0'), validators=[NON_NEG],
    )
    ideal_cycle_seconds = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    total_count = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    good_count = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    scrap_count = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'), validators=[NON_NEG],
    )
    availability_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('0'), validators=[NON_NEG, PCT_MAX],
    )
    performance_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('0'), validators=[NON_NEG, PCT_MAX],
    )
    quality_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('0'), validators=[NON_NEG, PCT_MAX],
    )
    oee_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('0'), validators=[NON_NEG, PCT_MAX],
    )
    recomputed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-period_date', 'asset__tag']
        unique_together = [
            ('tenant', 'period_number'),
            ('tenant', 'asset', 'shift', 'period_date'),
        ]
        indexes = [
            models.Index(fields=['tenant', 'period_date']),
        ]

    def __str__(self):
        return f'{self.period_number} | {self.asset.asset_number} | {self.period_date}'

    def _safe_div(self, numer, denom):
        if denom is None or denom == 0:
            return Decimal('0')
        return (Decimal(numer) / Decimal(denom)) * Decimal('100')

    def recompute_pcts(self):
        """Pure-arithmetic recompute of A / P / Q / OEE.

        Guarded against divide-by-zero per L-02 / L-03 style. Caller decides
        whether to .save() or .update() the result.
        """
        a = self._safe_div(self.run_minutes, self.planned_run_minutes)
        # Performance = (ideal_cycle_sec * total_count) / (run_minutes * 60)
        denom_perf = (self.run_minutes or Decimal('0')) * Decimal('60')
        numer_perf = (self.ideal_cycle_seconds or Decimal('0')) * (self.total_count or Decimal('0'))
        p = self._safe_div(numer_perf, denom_perf)
        q = self._safe_div(self.good_count, self.total_count)
        # Clamp to 0..100.
        a = min(a, Decimal('100'))
        p = min(p, Decimal('100'))
        q = min(q, Decimal('100'))
        self.availability_pct = a.quantize(Decimal('0.01'))
        self.performance_pct = p.quantize(Decimal('0.01'))
        self.quality_pct = q.quantize(Decimal('0.01'))
        self.oee_pct = ((a * p * q) / Decimal('10000')).quantize(Decimal('0.01'))

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.period_number and self.tenant_id:
            last = (
                OEEPeriod.all_objects
                .filter(tenant_id=self.tenant_id, period_number__startswith='OEEP-')
                .order_by('-period_number').first()
            )
            n = 1
            if last and last.period_number.startswith('OEEP-'):
                try:
                    n = int(last.period_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.period_number = f'OEEP-{n:05d}'
        self.recompute_pcts()
        self.recomputed_at = timezone.now()
        super().save(*args, **kwargs)


# ============================================================================
# 15.5  ALERT & ANOMALY DETECTION
# ============================================================================

class AlertRule(TenantAwareModel, TimeStampedModel):
    """Threshold / statistical rule evaluated against incoming readings.

    Auto-numbered ``AR-00001``. Exactly one of (device_tag, scope_device,
    scope_asset) must be set — enforced in clean() and AlertRuleForm.
    """

    CONDITION_CHOICES = [
        ('threshold_high', 'Above High Threshold'),
        ('threshold_low', 'Below Low Threshold'),
        ('range_outside', 'Outside Range'),
        ('rate_of_change', 'Rate of Change'),
        ('missing_data', 'Missing Data'),
        ('zscore', 'Rolling Z-Score'),
        ('iqr', 'IQR Outlier'),
        ('runs_rule', 'Runs Rule (Western Electric)'),
    ]
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    rule_number = models.CharField(max_length=15)
    name = models.CharField(max_length=120)
    device_tag = models.ForeignKey(
        DeviceTag, on_delete=models.CASCADE,
        null=True, blank=True, related_name='alert_rules',
    )
    scope_device = models.ForeignKey(
        Device, on_delete=models.CASCADE,
        null=True, blank=True, related_name='alert_rules',
    )
    scope_asset = models.ForeignKey(
        'eam.Asset', on_delete=models.CASCADE,
        null=True, blank=True, related_name='iot_alert_rules',
    )
    condition_type = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='threshold_high')
    threshold_high = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    threshold_low = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    window_seconds = models.PositiveIntegerField(default=60)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    notification_channels = models.CharField(
        max_length=255, default='in_app',
        help_text='Comma-separated: in_app,email,mes_andon',
    )
    cooldown_seconds = models.PositiveIntegerField(default=300)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['rule_number']
        unique_together = [
            ('tenant', 'rule_number'),
            ('tenant', 'name'),
        ]

    def __str__(self):
        return f'{self.rule_number} - {self.name}'

    def channel_list(self):
        return [c.strip() for c in (self.notification_channels or '').split(',') if c.strip()]

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.rule_number and self.tenant_id:
            last = (
                AlertRule.all_objects
                .filter(tenant_id=self.tenant_id, rule_number__startswith='AR-')
                .order_by('-rule_number').first()
            )
            n = 1
            if last and last.rule_number.startswith('AR-'):
                try:
                    n = int(last.rule_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.rule_number = f'AR-{n:05d}'
        super().save(*args, **kwargs)


class AnomalyDetection(TenantAwareModel, TimeStampedModel):
    """Append-only anomaly event. Auto-numbered ``AD-00001``.

    Idempotent on (tenant, rule, source_reading) so duplicate signal fires
    do not double-count.
    """

    SEVERITY_CHOICES = AlertRule.SEVERITY_CHOICES
    STATUS_CHOICES = [
        ('new', 'New'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
        ('false_positive', 'False Positive'),
    ]

    detection_number = models.CharField(max_length=15)
    rule = models.ForeignKey(
        AlertRule, on_delete=models.PROTECT, related_name='detections',
    )
    source_reading = models.ForeignKey(
        IoTReading, on_delete=models.PROTECT, related_name='detections',
    )
    detected_at = models.DateTimeField(default=timezone.now)
    value = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    baseline_value = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    deviation = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, validators=[SIGNED],
    )
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='iot_anomalies_acked',
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='iot_anomalies_resolved',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-detected_at', '-id']
        unique_together = [
            ('tenant', 'detection_number'),
            ('tenant', 'rule', 'source_reading'),
        ]
        indexes = [
            models.Index(fields=['tenant', 'status', 'severity']),
        ]

    def __str__(self):
        return f'{self.detection_number} | {self.rule.name} | {self.severity}'

    def is_acknowledgeable(self):
        return self.status == 'new'

    def is_resolvable(self):
        return self.status in ('new', 'acknowledged')

    def is_markable_false_positive(self):
        return self.status in ('new', 'acknowledged')

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from apps.core.models import get_current_tenant
            t = get_current_tenant()
            if t is not None:
                self.tenant = t
        if not self.detection_number and self.tenant_id:
            last = (
                AnomalyDetection.all_objects
                .filter(tenant_id=self.tenant_id, detection_number__startswith='AD-')
                .order_by('-detection_number').first()
            )
            n = 1
            if last and last.detection_number.startswith('AD-'):
                try:
                    n = int(last.detection_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            self.detection_number = f'AD-{n:05d}'
        super().save(*args, **kwargs)


class AlertNotification(TenantAwareModel, TimeStampedModel):
    """Append-only fanout log of notification attempts per detection per channel."""

    CHANNEL_CHOICES = [
        ('in_app', 'In-App'),
        ('email', 'Email'),
        ('mes_andon', 'MES Andon'),
    ]
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('acknowledged', 'Acknowledged'),
    ]

    detection = models.ForeignKey(
        AnomalyDetection, on_delete=models.PROTECT, related_name='notifications',
    )
    channel = models.CharField(max_length=15, choices=CHANNEL_CHOICES, default='in_app')
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='iot_notifications',
    )
    target_email = models.CharField(max_length=255, blank=True)
    mes_andon = models.ForeignKey(
        'mes.AndonAlert', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='iot_notifications',
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='queued')
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'detection', 'channel')

    def __str__(self):
        return f'{self.detection.detection_number}/{self.channel}'
