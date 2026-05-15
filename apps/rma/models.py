"""Module 18 - Returns & RMA Management.

Sub-modules:
    18.1  RMA Request & Authorization
            (RMAReason, RMARequest, RMALine, RMAApproval)
    18.2  Returns Receiving & Inspection
            (ReturnReceipt, ReturnReceiptLine)
    18.3  Repair & Refurbishment Tracking
            (RepairOrder, RepairPartUsage, RepairLaborLog)
    18.4  Warranty Management
            (WarrantyPolicy, WarrantyRegistration, WarrantyClaim)
    18.5  Returns Analytics
            (FailureMode, RootCauseCategory, ReturnAnalysis, SupplierChargeback)

Cross-module integration (see apps/rma/signals.py):
    - RMARequest.status='approved'         -> draft ReturnReceipt
    - ReturnReceiptLine.disposition='restock'  -> inventory.StockMovement(receipt)
    - ReturnReceiptLine.disposition in {repair,refurbish} -> draft RepairOrder
    - RepairLaborLog.post_save             -> labor.LaborBooking
    - WarrantyClaim.status='approved' + resolution='replace' -> draft sales.SalesOrder
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel
from apps.rma.services.numbering import next_code
from apps.rma.services.warranty import compute_warranty_end


# ============================================================================
# 18.1  RMA REQUEST & AUTHORIZATION
# ============================================================================

class RMAReason(TenantAwareModel, TimeStampedModel):
    """Tenant catalog of return reason codes (why a customer is returning)."""

    CATEGORY_CHOICES = [
        ('quality_defect', 'Quality Defect'),
        ('shipping_damage', 'Shipping Damage'),
        ('wrong_item', 'Wrong Item Shipped'),
        ('customer_change', 'Customer Change of Mind'),
        ('warranty', 'Warranty Claim'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=120)
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default='quality_defect',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'name')

    def __str__(self):
        return self.name


class RMARequest(TenantAwareModel, TimeStampedModel):
    """Customer return request. Root of the returns workflow.

    Workflow:  draft -> submitted -> approved | rejected  (plus cancelled).
    Approving an RMA auto-drafts a ReturnReceipt (see signals).
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    ACTION_CHOICES = [
        ('refund', 'Refund'),
        ('replace', 'Replacement'),
        ('repair', 'Repair & Return'),
        ('credit_note', 'Credit Note'),
    ]

    code = models.CharField(max_length=20, blank=True)
    customer = models.ForeignKey(
        'sales.Customer', on_delete=models.PROTECT, related_name='rma_requests',
    )
    sales_order = models.ForeignKey(
        'sales.SalesOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rma_requests',
    )
    sales_invoice = models.ForeignKey(
        'sales.SalesInvoice', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rma_requests',
    )
    request_date = models.DateField(default=timezone.now)
    requested_action = models.CharField(
        max_length=20, choices=ACTION_CHOICES, default='refund',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    customer_reference = models.CharField(
        max_length=80, blank=True,
        help_text='Customer-supplied complaint / ticket reference (free text).',
    )
    reason_summary = models.CharField(max_length=255, blank=True)
    customer_notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)

    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='decided_rma_requests',
    )
    decision_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_rma_requests',
    )

    class Meta:
        ordering = ['-request_date', '-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'(draft RMA #{self.pk})'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(RMARequest, self.tenant, 'RMA')
        super().save(*args, **kwargs)

    def is_editable(self):
        return self.status in ('draft',)

    def can_submit(self):
        return self.status == 'draft' and self.lines.exists()

    def can_approve(self):
        return self.status == 'submitted'

    def can_reject(self):
        return self.status == 'submitted'

    def can_cancel(self):
        return self.status in ('draft', 'submitted', 'approved')


class RMALine(TenantAwareModel, TimeStampedModel):
    """One returned product line on an RMA request."""

    CONDITION_CHOICES = [
        ('unopened', 'Unopened / Sealed'),
        ('opened_unused', 'Opened, Unused'),
        ('used', 'Used'),
        ('damaged', 'Damaged'),
        ('defective', 'Defective / Not Working'),
    ]

    rma = models.ForeignKey(
        RMARequest, on_delete=models.CASCADE, related_name='lines',
    )
    line_no = models.PositiveIntegerField(default=1)
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='rma_lines',
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    reason = models.ForeignKey(
        RMAReason, on_delete=models.PROTECT, related_name='rma_lines',
    )
    condition_reported = models.CharField(
        max_length=20, choices=CONDITION_CHOICES, default='defective',
    )
    lot_number = models.CharField(max_length=60, blank=True)
    serial_number = models.CharField(max_length=120, blank=True)
    line_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['rma', 'line_no']
        unique_together = ('rma', 'line_no')

    def __str__(self):
        return f'{self.rma.code} L{self.line_no}'

    def save(self, *args, **kwargs):
        if self._state.adding:
            existing = (
                RMALine.all_objects.filter(rma=self.rma)
                .exclude(pk=self.pk).order_by('-line_no').first()
            )
            self.line_no = (existing.line_no + 1) if existing else 1
        super().save(*args, **kwargs)

    @property
    def line_value(self) -> Decimal:
        return (self.quantity or Decimal('0')) * (self.unit_price or Decimal('0'))


class RMAApproval(TenantAwareModel, TimeStampedModel):
    """Append-only authorization audit trail for RMARequest transitions."""

    ACTION_CHOICES = [
        ('submit', 'Submit'),
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('cancel', 'Cancel'),
    ]

    rma = models.ForeignKey(
        RMARequest, on_delete=models.CASCADE, related_name='approvals',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rma_approvals',
    )
    performed_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-performed_at', '-id']

    def __str__(self):
        return f'{self.rma.code} {self.action} {self.from_status}->{self.to_status}'


# ============================================================================
# 18.2  RETURNS RECEIVING & INSPECTION
# ============================================================================

class ReturnReceipt(TenantAwareModel, TimeStampedModel):
    """Physical receipt of returned goods against an authorized RMA.

    Workflow:  draft -> inspecting -> completed  (plus cancelled).
    Auto-drafted by the RMARequest approval signal (idempotent on `rma`).
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('inspecting', 'Inspecting'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    code = models.CharField(max_length=20, blank=True)
    rma = models.ForeignKey(
        RMARequest, on_delete=models.PROTECT, related_name='receipts',
    )
    warehouse = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='return_receipts',
    )
    received_date = models.DateField(default=timezone.now)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='received_return_receipts',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    carrier_name = models.CharField(max_length=120, blank=True)
    tracking_number = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-received_date', '-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'(draft RR #{self.pk})'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(ReturnReceipt, self.tenant, 'RR')
        super().save(*args, **kwargs)

    def is_editable(self):
        return self.status in ('draft', 'inspecting')

    def can_start_inspection(self):
        return self.status == 'draft' and self.lines.exists()

    def can_complete(self):
        return self.status == 'inspecting'

    def can_cancel(self):
        return self.status in ('draft', 'inspecting')


class ReturnReceiptLine(TenantAwareModel, TimeStampedModel):
    """Inspected line of a return receipt: condition + disposition routing.

    `disposition` drives the post_save signal:
        restock              -> inventory.StockMovement(receipt)
        repair / refurbish   -> draft rma.RepairOrder
    `disposition_done` is the idempotency latch so the signal fires once.
    """

    CONDITION_CHOICES = [
        ('new', 'New / Resalable'),
        ('like_new', 'Like New'),
        ('used', 'Used - Functional'),
        ('damaged', 'Damaged'),
        ('defective', 'Defective'),
        ('scrap', 'Scrap'),
    ]
    DISPOSITION_CHOICES = [
        ('restock', 'Restock to Inventory'),
        ('repair', 'Route to Repair'),
        ('refurbish', 'Route to Refurbishment'),
        ('scrap', 'Scrap'),
        ('return_to_supplier', 'Return to Supplier'),
        ('quarantine', 'Quarantine - Pending Review'),
    ]

    receipt = models.ForeignKey(
        ReturnReceipt, on_delete=models.CASCADE, related_name='lines',
    )
    rma_line = models.ForeignKey(
        RMALine, on_delete=models.PROTECT, related_name='receipt_lines',
    )
    quantity_received = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0'))],
    )
    condition_assessed = models.CharField(
        max_length=20, choices=CONDITION_CHOICES, default='defective',
    )
    disposition = models.CharField(
        max_length=20, choices=DISPOSITION_CHOICES, default='quarantine',
    )
    inspection_notes = models.TextField(blank=True)
    inspected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='inspected_receipt_lines',
    )
    # Idempotency latch + provenance for the disposition-routing signal.
    disposition_done = models.BooleanField(default=False)
    stock_movement = models.ForeignKey(
        'inventory.StockMovement', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rma_receipt_lines',
    )

    class Meta:
        ordering = ['receipt', 'id']

    def __str__(self):
        return f'{self.receipt.code} - {self.rma_line.product}'


# ============================================================================
# 18.3  REPAIR & REFURBISHMENT TRACKING
# ============================================================================

class RepairOrder(TenantAwareModel, TimeStampedModel):
    """Rework / refurbishment ticket for a returned unit.

    Workflow:  draft -> in_progress -> completed  (plus on_hold, cancelled).
    Auto-drafted from a ReturnReceiptLine with disposition repair/refurbish.
    `actual_cost` + `labor_minutes` are denorms owned by
    `services/repair.recompute_repair_costs`.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    TYPE_CHOICES = [
        ('repair', 'Repair'),
        ('refurbishment', 'Refurbishment'),
    ]

    code = models.CharField(max_length=20, blank=True)
    receipt_line = models.ForeignKey(
        ReturnReceiptLine, on_delete=models.PROTECT,
        null=True, blank=True, related_name='repair_orders',
    )
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='repair_orders',
    )
    order_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default='repair',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    problem_description = models.TextField(blank=True)
    repair_instructions = models.TextField(blank=True)
    resolution_notes = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_repair_orders',
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    estimated_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    # Denorms - recomputed by services/repair.recompute_repair_costs.
    actual_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    labor_minutes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'(draft REP #{self.pk})'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(RepairOrder, self.tenant, 'REP')
        super().save(*args, **kwargs)

    def is_editable(self):
        return self.status in ('draft', 'in_progress', 'on_hold')

    def can_start(self):
        return self.status == 'draft'

    def can_hold(self):
        return self.status == 'in_progress'

    def can_resume(self):
        return self.status == 'on_hold'

    def can_complete(self):
        return self.status in ('in_progress', 'on_hold')

    def can_cancel(self):
        return self.status not in ('completed', 'cancelled')


class RepairPartUsage(TenantAwareModel, TimeStampedModel):
    """Append-only ledger of replacement parts consumed by a repair order."""

    repair_order = models.ForeignKey(
        RepairOrder, on_delete=models.CASCADE, related_name='part_usages',
    )
    part = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='rma_part_usages',
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    unit_cost = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    # Denorm - quantity * unit_cost, computed in save().
    line_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    stock_movement = models.ForeignKey(
        'inventory.StockMovement', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rma_part_usages',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['repair_order', 'id']

    def __str__(self):
        return f'{self.repair_order.code} - {self.part}'

    def save(self, *args, **kwargs):
        self.line_cost = (
            (self.quantity or Decimal('0')) * (self.unit_cost or Decimal('0'))
        ).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)


class RepairLaborLog(TenantAwareModel, TimeStampedModel):
    """Append-only labor ledger for a repair order.

    `labor_cost` is computed in save() (minutes / 60 * hourly_rate). A
    post_save signal mirrors each row into a labor.LaborBooking.
    """

    repair_order = models.ForeignKey(
        RepairOrder, on_delete=models.CASCADE, related_name='labor_logs',
    )
    employee = models.ForeignKey(
        'labor.Employee', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rma_labor_logs',
    )
    work_date = models.DateField(default=timezone.now)
    minutes = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0)],
    )
    hourly_rate = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    # Denorm - minutes / 60 * hourly_rate, computed in save().
    labor_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    labor_booking = models.ForeignKey(
        'labor.LaborBooking', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rma_labor_logs',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['repair_order', '-work_date', '-id']

    def __str__(self):
        return f'{self.repair_order.code} - {self.minutes}min'

    def save(self, *args, **kwargs):
        self.labor_cost = (
            Decimal(self.minutes or 0) * (self.hourly_rate or Decimal('0'))
            / Decimal('60')
        ).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)


# ============================================================================
# 18.4  WARRANTY MANAGEMENT
# ============================================================================

class WarrantyPolicy(TenantAwareModel, TimeStampedModel):
    """Reusable warranty terms template (duration + coverage scope)."""

    COVERAGE_CHOICES = [
        ('parts', 'Parts Only'),
        ('labor', 'Labor Only'),
        ('parts_and_labor', 'Parts & Labor'),
        ('full', 'Full Coverage'),
    ]

    code = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=120)
    coverage_type = models.CharField(
        max_length=20, choices=COVERAGE_CHOICES, default='parts_and_labor',
    )
    duration_months = models.PositiveIntegerField(
        default=12, validators=[MinValueValidator(1), MaxValueValidator(600)],
    )
    terms = models.TextField(blank=True)
    product = models.ForeignKey(
        'plm.Product', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='warranty_policies',
        help_text='Optional - restrict this policy to one product.',
    )
    product_category = models.ForeignKey(
        'plm.ProductCategory', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='warranty_policies',
        help_text='Optional - restrict this policy to one product category.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}' if self.code else self.name

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(WarrantyPolicy, self.tenant, 'WP')
        super().save(*args, **kwargs)


class WarrantyRegistration(TenantAwareModel, TimeStampedModel):
    """A specific product unit registered under a warranty policy.

    `end_date` is computed in save() = start_date + policy.duration_months.
    `status` time-driven `active -> expired` flip is owned by the
    `expire_warranties` management command (see L-21).
    """

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('void', 'Void'),
        ('claimed', 'Claimed'),
    ]

    code = models.CharField(max_length=20, blank=True)
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='warranty_registrations',
    )
    customer = models.ForeignKey(
        'sales.Customer', on_delete=models.PROTECT, related_name='warranty_registrations',
    )
    policy = models.ForeignKey(
        WarrantyPolicy, on_delete=models.PROTECT, related_name='registrations',
    )
    sales_order = models.ForeignKey(
        'sales.SalesOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='warranty_registrations',
    )
    serial_number = models.CharField(max_length=120, blank=True)
    purchase_date = models.DateField(default=timezone.now)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_date', '-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'(WR #{self.pk})'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(WarrantyRegistration, self.tenant, 'WR')
        if self.start_date and self.policy_id:
            self.end_date = compute_warranty_end(
                self.start_date, self.policy.duration_months,
            )
        super().save(*args, **kwargs)

    @property
    def days_remaining(self):
        if not self.end_date:
            return None
        return (self.end_date - timezone.now().date()).days

    @property
    def is_expiring_soon(self):
        """True when an active warranty ends within 30 days."""
        d = self.days_remaining
        return self.status == 'active' and d is not None and 0 <= d <= 30


class WarrantyClaim(TenantAwareModel, TimeStampedModel):
    """A claim filed against a warranty registration.

    Workflow:  submitted -> validated -> approved | rejected -> fulfilled.
    An approved claim with resolution='replace' auto-drafts a replacement
    sales.SalesOrder (idempotent on `replacement_order` FK; see signals).
    """

    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('validated', 'Validated'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('fulfilled', 'Fulfilled'),
    ]
    RESOLUTION_CHOICES = [
        ('repair', 'Repair'),
        ('replace', 'Replacement'),
        ('refund', 'Refund'),
        ('credit', 'Credit Note'),
    ]

    code = models.CharField(max_length=20, blank=True)
    registration = models.ForeignKey(
        WarrantyRegistration, on_delete=models.PROTECT, related_name='claims',
    )
    rma = models.ForeignKey(
        RMARequest, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='warranty_claims',
    )
    claim_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    defect_description = models.TextField(blank=True)
    resolution = models.CharField(
        max_length=20, choices=RESOLUTION_CHOICES, default='repair',
    )
    validation_notes = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='decided_warranty_claims',
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    replacement_order = models.ForeignKey(
        'sales.SalesOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='warranty_replacement_claims',
    )

    class Meta:
        ordering = ['-claim_date', '-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'(WC #{self.pk})'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(WarrantyClaim, self.tenant, 'WC')
        super().save(*args, **kwargs)

    def can_validate(self):
        return self.status == 'submitted'

    def can_approve(self):
        return self.status == 'validated'

    def can_reject(self):
        return self.status in ('submitted', 'validated')

    def can_fulfill(self):
        return self.status == 'approved'


# ============================================================================
# 18.5  RETURNS ANALYTICS
# ============================================================================

class FailureMode(TenantAwareModel, TimeStampedModel):
    """Tenant catalog of FMEA-style failure modes for return categorization."""

    CATEGORY_CHOICES = [
        ('electrical', 'Electrical'),
        ('mechanical', 'Mechanical'),
        ('software', 'Software / Firmware'),
        ('cosmetic', 'Cosmetic'),
        ('material', 'Material / Component'),
        ('process', 'Process / Assembly'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=120)
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default='mechanical',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'name')

    def __str__(self):
        return self.name


class RootCauseCategory(TenantAwareModel, TimeStampedModel):
    """Tenant catalog of root-cause categories with a responsible area."""

    AREA_CHOICES = [
        ('design', 'Design / Engineering'),
        ('manufacturing', 'Manufacturing'),
        ('supplier', 'Supplier / Component'),
        ('logistics', 'Logistics / Shipping'),
        ('installation', 'Installation / Setup'),
        ('user_error', 'User Error'),
        ('unknown', 'Unknown'),
    ]

    name = models.CharField(max_length=120)
    responsible_area = models.CharField(
        max_length=20, choices=AREA_CHOICES, default='manufacturing',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'name')
        verbose_name_plural = 'Root cause categories'

    def __str__(self):
        return self.name


class ReturnAnalysis(TenantAwareModel, TimeStampedModel):
    """Root-cause + failure-mode analysis of a single returned line."""

    code = models.CharField(max_length=20, blank=True)
    rma_line = models.ForeignKey(
        RMALine, on_delete=models.PROTECT, related_name='analyses',
    )
    failure_mode = models.ForeignKey(
        FailureMode, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='analyses',
    )
    root_cause_category = models.ForeignKey(
        RootCauseCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='analyses',
    )
    supplier = models.ForeignKey(
        'procurement.Supplier', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rma_analyses',
        help_text='Set when the root cause is attributable to a supplier.',
    )
    analysis_notes = models.TextField(blank=True)
    corrective_action = models.TextField(blank=True)
    analyzed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='return_analyses',
    )
    analyzed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-analyzed_at', '-id']
        unique_together = ('tenant', 'code')
        verbose_name_plural = 'Return analyses'

    def __str__(self):
        return self.code or f'(RA #{self.pk})'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(ReturnAnalysis, self.tenant, 'RA')
        super().save(*args, **kwargs)


class SupplierChargeback(TenantAwareModel, TimeStampedModel):
    """Cost recovery raised against a supplier for a supplier-caused return.

    Workflow:  draft -> pending -> issued -> disputed -> recovered | written_off.
    Transitions are guarded by `services/chargeback.apply_transition`.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('issued', 'Issued'),
        ('disputed', 'Disputed'),
        ('recovered', 'Recovered'),
        ('written_off', 'Written Off'),
    ]

    code = models.CharField(max_length=20, blank=True)
    analysis = models.ForeignKey(
        ReturnAnalysis, on_delete=models.PROTECT, related_name='chargebacks',
    )
    supplier = models.ForeignKey(
        'procurement.Supplier', on_delete=models.PROTECT, related_name='rma_chargebacks',
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    issued_date = models.DateField(null=True, blank=True)
    recovered_date = models.DateField(null=True, blank=True)
    reference = models.CharField(
        max_length=80, blank=True,
        help_text='Debit note / credit memo reference (free text).',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'(SCB #{self.pk})'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            self.code = next_code(SupplierChargeback, self.tenant, 'SCB')
        super().save(*args, **kwargs)
