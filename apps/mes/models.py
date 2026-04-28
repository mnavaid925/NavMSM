"""Module 6 - Shop Floor Control (MES).

Sub-modules:
    6.1  Work Order Execution             (MESWorkOrder, MESWorkOrderOperation)
    6.2  Operator Terminal Interface      (ShopFloorOperator, OperatorTimeLog)
    6.3  Production Reporting             (ProductionReport)
    6.4  Andon & Alert Management         (AndonAlert)
    6.5  Paperless Work Instructions      (WorkInstruction,
                                           WorkInstructionVersion,
                                           WorkInstructionAcknowledgement)

Reuses:
    apps.plm.models.Product               - part master / SOP linkage
    apps.pps.models.ProductionOrder       - source of dispatched work orders
    apps.pps.models.RoutingOperation      - source of work-order operations
    apps.pps.models.WorkCenter            - operation execution location
    apps.accounts.models.User             - actor / operator identity

Note:
    A MESWorkOrder is a child record of a pps.ProductionOrder. The PPS order
    remains the system-of-record for "what to build"; MES owns "who built it,
    when, and how it went". Decoupling lets PPS scheduling and MES execution
    evolve independently.
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TenantAwareModel, TimeStampedModel
from apps.plm.models import Product
from apps.pps.models import ProductionOrder, RoutingOperation, WorkCenter


# ============================================================================
# 6.1  WORK ORDER EXECUTION
# ============================================================================

class MESWorkOrder(TenantAwareModel, TimeStampedModel):
    """Shop-floor execution record dispatched from a pps.ProductionOrder.

    The PPS order is the system-of-record for "what to build". MES owns the
    real-time execution lifecycle: dispatched -> in_progress -> completed,
    with optional on_hold and cancelled paths.
    """

    STATUS_CHOICES = [
        ('dispatched', 'Dispatched'),
        ('in_progress', 'In Progress'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('rush', 'Rush'),
    ]

    wo_number = models.CharField(max_length=30)
    production_order = models.ForeignKey(
        ProductionOrder, on_delete=models.PROTECT, related_name='mes_work_orders',
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='mes_work_orders',
    )
    quantity_to_build = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    quantity_completed = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    quantity_scrapped = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='dispatched')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    dispatched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mes_work_orders_dispatched',
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mes_work_orders_completed',
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'wo_number')
        verbose_name = 'MES Work Order'

    def __str__(self):
        return f'{self.wo_number} -> {self.product.sku} x {self.quantity_to_build}'

    def is_editable(self):
        return self.status in ('dispatched', 'on_hold')

    def can_start(self):
        return self.status in ('dispatched', 'on_hold')

    def can_hold(self):
        return self.status == 'in_progress'

    def can_complete(self):
        return self.status == 'in_progress'

    def can_cancel(self):
        return self.status not in ('completed', 'cancelled')


class MESWorkOrderOperation(TenantAwareModel, TimeStampedModel):
    """One operation step inside a MESWorkOrder, fanned out from a routing op."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('setup', 'Setup'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('skipped', 'Skipped'),
    ]

    work_order = models.ForeignKey(
        MESWorkOrder, on_delete=models.CASCADE, related_name='operations',
    )
    routing_operation = models.ForeignKey(
        RoutingOperation, on_delete=models.PROTECT,
        related_name='mes_work_order_operations',
    )
    sequence = models.PositiveIntegerField(default=10)
    operation_name = models.CharField(max_length=255)
    work_center = models.ForeignKey(
        WorkCenter, on_delete=models.PROTECT,
        related_name='mes_work_order_operations',
    )
    setup_minutes = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    run_minutes_per_unit = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    planned_minutes = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    actual_minutes = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    total_good_qty = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    total_scrap_qty = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    total_rework_qty = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    current_operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mes_active_operations',
    )

    class Meta:
        ordering = ['work_order', 'sequence']
        unique_together = ('work_order', 'sequence')
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'current_operator']),
        ]
        verbose_name = 'MES Work Order Operation'

    def __str__(self):
        return f'{self.work_order.wo_number} #{self.sequence:03d} {self.operation_name}'

    def is_open(self):
        return self.status in ('pending', 'setup', 'running', 'paused')

    def can_start(self):
        return self.status in ('pending', 'paused', 'setup')

    def can_pause(self):
        return self.status == 'running'

    def can_resume(self):
        return self.status == 'paused'

    def can_stop(self):
        return self.status in ('running', 'paused', 'setup')


# ============================================================================
# 6.2  OPERATOR TERMINAL INTERFACE
# ============================================================================

class ShopFloorOperator(TenantAwareModel, TimeStampedModel):
    """Thin profile layer over accounts.User for shop-floor identity.

    Lets us issue badge numbers, set a default work center, and enable / disable
    floor access without touching the auth User. A future kiosk-mode badge-scan
    login would key off ``badge_number``.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='shop_floor_operator',
    )
    badge_number = models.CharField(max_length=15)
    default_work_center = models.ForeignKey(
        WorkCenter, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='default_operators',
    )
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['badge_number']
        unique_together = ('tenant', 'badge_number')
        verbose_name = 'Shop Floor Operator'

    def __str__(self):
        return f'{self.badge_number} - {self.user.get_full_name() or self.user.username}'


class OperatorTimeLog(TenantAwareModel, TimeStampedModel):
    """Append-only event log of operator actions on the floor.

    Clock-in/out are not pegged to an operation. Start/Pause/Resume/Stop on
    a job all attach to a MESWorkOrderOperation.
    """

    ACTION_CHOICES = [
        ('clock_in', 'Clock In'),
        ('clock_out', 'Clock Out'),
        ('start_job', 'Start Job'),
        ('pause_job', 'Pause Job'),
        ('resume_job', 'Resume Job'),
        ('stop_job', 'Stop Job'),
    ]

    operator = models.ForeignKey(
        ShopFloorOperator, on_delete=models.CASCADE, related_name='time_logs',
    )
    work_order_operation = models.ForeignKey(
        MESWorkOrderOperation, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='time_logs',
    )
    action = models.CharField(max_length=15, choices=ACTION_CHOICES)
    recorded_at = models.DateTimeField()
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['tenant', 'operator', 'recorded_at']),
            models.Index(fields=['tenant', 'work_order_operation', 'action']),
        ]
        verbose_name = 'Operator Time Log'

    def __str__(self):
        return f'{self.operator.badge_number} {self.get_action_display()} at {self.recorded_at:%Y-%m-%d %H:%M}'


# ============================================================================
# 6.3  PRODUCTION REPORTING
# ============================================================================

class ProductionReport(TenantAwareModel, TimeStampedModel):
    """Operator-filed quantity / scrap / rework report against an operation."""

    SCRAP_REASON_CHOICES = [
        ('material_defect', 'Material Defect'),
        ('setup_error', 'Setup Error'),
        ('tooling', 'Tooling'),
        ('process', 'Process'),
        ('operator_error', 'Operator Error'),
        ('other', 'Other'),
    ]

    work_order_operation = models.ForeignKey(
        MESWorkOrderOperation, on_delete=models.CASCADE,
        related_name='production_reports',
    )
    good_qty = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    scrap_qty = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    rework_qty = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    scrap_reason = models.CharField(
        max_length=30, choices=SCRAP_REASON_CHOICES, blank=True,
    )
    cycle_time_minutes = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0'))],
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mes_production_reports',
    )
    reported_at = models.DateTimeField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-reported_at']
        indexes = [
            models.Index(fields=['tenant', 'work_order_operation', 'reported_at']),
        ]
        verbose_name = 'Production Report'

    def __str__(self):
        return f'{self.work_order_operation} good {self.good_qty} scrap {self.scrap_qty}'


# ============================================================================
# 6.4  ANDON & ALERT MANAGEMENT
# ============================================================================

class AndonAlert(TenantAwareModel, TimeStampedModel):
    """Real-time visual alert raised from the floor."""

    ALERT_TYPE_CHOICES = [
        ('quality', 'Quality'),
        ('material', 'Material'),
        ('equipment', 'Equipment'),
        ('safety', 'Safety'),
        ('other', 'Other'),
    ]
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
        ('cancelled', 'Cancelled'),
    ]

    alert_number = models.CharField(max_length=30)
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES, default='quality')
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    work_center = models.ForeignKey(
        WorkCenter, on_delete=models.PROTECT, related_name='andon_alerts',
    )
    work_order = models.ForeignKey(
        MESWorkOrder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='andon_alerts',
    )
    work_order_operation = models.ForeignKey(
        MESWorkOrderOperation, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='andon_alerts',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='andon_alerts_raised',
    )
    raised_at = models.DateTimeField()
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='andon_alerts_acknowledged',
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='andon_alerts_resolved',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-severity', '-raised_at']
        unique_together = ('tenant', 'alert_number')
        indexes = [
            models.Index(fields=['tenant', 'status', 'severity']),
            models.Index(fields=['tenant', 'work_center', 'status']),
        ]
        verbose_name = 'Andon Alert'

    def __str__(self):
        return f'{self.alert_number} {self.get_alert_type_display()} {self.get_severity_display()}'

    def can_acknowledge(self):
        return self.status == 'open'

    def can_resolve(self):
        return self.status in ('open', 'acknowledged')

    def can_cancel(self):
        return self.status in ('open', 'acknowledged')


# ============================================================================
# 6.5  PAPERLESS WORK INSTRUCTIONS
# ============================================================================

WORK_INSTRUCTION_FILE_EXT_ALLOWLIST = (
    '.pdf', '.png', '.jpg', '.jpeg', '.mp4',
    '.docx', '.xlsx', '.txt',
)
WORK_INSTRUCTION_FILE_MAX_BYTES = 25 * 1024 * 1024  # 25 MB


def _work_instruction_upload_path(instance, filename):
    """Files land under media/mes/work_instructions/<tenant>/<instruction>/."""
    tenant_id = instance.instruction.tenant_id if instance.instruction_id else 'unscoped'
    inst_id = instance.instruction_id or 'orphan'
    return f'mes/work_instructions/{tenant_id}/{inst_id}/{filename}'


class WorkInstruction(TenantAwareModel, TimeStampedModel):
    """Digital SOP card. Each release is an immutable WorkInstructionVersion.

    ``current_version`` always points at the released version for the operator
    to see; the Version model carries the actual content + attachment.
    """

    DOC_TYPE_CHOICES = [
        ('sop', 'Standard Operating Procedure'),
        ('setup_sheet', 'Setup Sheet'),
        ('quality_check', 'Quality Check'),
        ('safety', 'Safety Procedure'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('released', 'Released'),
        ('obsolete', 'Obsolete'),
    ]

    instruction_number = models.CharField(max_length=30)
    title = models.CharField(max_length=255)
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES, default='sop')
    routing_operation = models.ForeignKey(
        RoutingOperation, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='work_instructions',
    )
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='work_instructions',
    )
    current_version = models.ForeignKey(
        'WorkInstructionVersion', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='work_instructions_created',
    )
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='work_instructions_released',
    )
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['instruction_number']
        unique_together = ('tenant', 'instruction_number')
        verbose_name = 'Work Instruction'

    def __str__(self):
        return f'{self.instruction_number} {self.title}'

    def clean(self):
        super().clean()
        if not self.routing_operation_id and not self.product_id:
            raise ValidationError(
                'A work instruction must be linked to either a routing operation or a product.'
            )

    def is_editable(self):
        return self.status == 'draft'


class WorkInstructionVersion(TenantAwareModel, TimeStampedModel):
    """An immutable revision of a WorkInstruction's content + attachment."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('released', 'Released'),
        ('obsolete', 'Obsolete'),
    ]

    instruction = models.ForeignKey(
        WorkInstruction, on_delete=models.CASCADE, related_name='versions',
    )
    version = models.CharField(max_length=20, help_text='e.g. 1.0, 1.1, 2.0')
    content = models.TextField(blank=True)
    attachment = models.FileField(
        upload_to=_work_instruction_upload_path, blank=True, null=True,
    )
    video_url = models.URLField(blank=True)
    change_notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='work_instruction_versions_uploaded',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['instruction', '-created_at']
        unique_together = ('instruction', 'version')
        verbose_name = 'Work Instruction Version'

    def __str__(self):
        return f'{self.instruction.instruction_number} v{self.version}'


class WorkInstructionAcknowledgement(TenantAwareModel, TimeStampedModel):
    """Operator acknowledgement of a specific version of an instruction.

    Stores the version string as a snapshot so a deleted Version row does not
    orphan past acknowledgements (they survive as historical evidence).
    """

    instruction = models.ForeignKey(
        WorkInstruction, on_delete=models.CASCADE, related_name='acknowledgements',
    )
    instruction_version = models.CharField(
        max_length=20,
        help_text='Snapshot of the version string at ack time.',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='work_instruction_acknowledgements',
    )
    acknowledged_at = models.DateTimeField(auto_now_add=True)
    signature_text = models.CharField(max_length=120)

    class Meta:
        ordering = ['-acknowledged_at']
        unique_together = ('tenant', 'instruction', 'user', 'instruction_version')
        indexes = [
            models.Index(fields=['tenant', 'user']),
            models.Index(fields=['tenant', 'instruction']),
        ]
        verbose_name = 'Work Instruction Acknowledgement'

    def __str__(self):
        return f'{self.user} ack {self.instruction.instruction_number} v{self.instruction_version}'
