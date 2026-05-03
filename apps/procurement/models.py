"""Module 9 - Procurement & Supplier Portal.

Sub-modules:
    9.1  Purchase Order Management        (Supplier, SupplierContact, PurchaseOrder,
                                           PurchaseOrderLine, PurchaseOrderRevision,
                                           PurchaseOrderApproval)
    9.2  Supplier Quotation & RFQ         (RequestForQuotation, RFQLine, RFQSupplier,
                                           SupplierQuotation, QuotationLine,
                                           QuotationAward)
    9.3  Supplier Performance Scorecard   (SupplierMetricEvent, SupplierScorecard)
    9.4  Supplier Self-Service Portal     (SupplierASN, SupplierASNLine,
                                           SupplierInvoice, SupplierInvoiceLine)
    9.5  Blanket Orders & Scheduling      (BlanketOrder, BlanketOrderLine,
                                           ScheduleRelease, ScheduleReleaseLine)

Cross-module integration (additive, nullable FKs):
    - apps.inventory.GoodsReceiptNote.supplier / .purchase_order
    - apps.qms.IncomingInspection.supplier / .purchase_order
    - apps.mrp.MRPPurchaseRequisition.converted_po
    - apps.accounts.User.role = 'supplier' + .supplier_company FK
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel


# ============================================================================
# 9.1  PURCHASE ORDER MANAGEMENT
# ============================================================================

class Supplier(TenantAwareModel, TimeStampedModel):
    """Vendor master record. Referenced by PO, RFQ, ASN, Invoice, Blanket order."""

    RISK_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    website = models.URLField(blank=True)
    tax_id = models.CharField(max_length=60, blank=True)
    address = models.TextField(blank=True)
    country = models.CharField(max_length=100, blank=True)
    currency = models.CharField(max_length=3, default='USD')
    payment_terms = models.CharField(max_length=60, blank=True, help_text='e.g. NET30')
    delivery_terms = models.CharField(max_length=60, blank=True, help_text='e.g. FOB')
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    risk_rating = models.CharField(max_length=10, choices=RISK_CHOICES, default='low')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['code']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}'


class SupplierContact(TenantAwareModel, TimeStampedModel):
    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name='contacts',
    )
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['supplier', '-is_primary', 'name']

    def __str__(self):
        return f'{self.name} ({self.supplier.code})'


class PurchaseOrder(TenantAwareModel, TimeStampedModel):
    """A purchase order issued to a supplier."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('acknowledged', 'Acknowledged'),
        ('in_progress', 'In Progress'),
        ('received', 'Received'),
        ('closed', 'Closed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('rush', 'Rush'),
    ]

    po_number = models.CharField(max_length=20)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='purchase_orders',
    )
    order_date = models.DateField(default=timezone.now)
    required_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default='USD')
    payment_terms = models.CharField(max_length=60, blank=True)
    delivery_terms = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_purchase_orders',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_purchase_orders',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='acknowledged_purchase_orders',
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    subtotal = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    tax_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    discount_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    grand_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )

    source_quotation = models.ForeignKey(
        'procurement.SupplierQuotation', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='spawned_purchase_orders',
    )
    blanket_order = models.ForeignKey(
        'procurement.BlanketOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='child_purchase_orders',
    )

    class Meta:
        ordering = ['-order_date', '-id']
        unique_together = ('tenant', 'po_number')

    def __str__(self):
        return self.po_number

    def save(self, *args, **kwargs):
        if not self.po_number and self.tenant_id:
            last = (
                PurchaseOrder.all_objects
                .filter(tenant=self.tenant)
                .order_by('-id')
                .first()
            )
            seq = (last.id + 1) if last else 1
            self.po_number = f'PUR-{seq:05d}'
        super().save(*args, **kwargs)

    def is_editable(self):
        return self.status in ('draft', 'rejected')

    def recompute_totals(self):
        """Recompute subtotal/tax/discount/grand_total from lines (denorm cache)."""
        agg = self.lines.aggregate(
            sub=models.Sum('line_subtotal'),
            tax=models.Sum('line_tax'),
            disc=models.Sum('line_discount'),
            tot=models.Sum('line_total'),
        )
        self.subtotal = agg['sub'] or Decimal('0')
        self.tax_total = agg['tax'] or Decimal('0')
        self.discount_total = agg['disc'] or Decimal('0')
        self.grand_total = agg['tot'] or Decimal('0')
        self.save(update_fields=[
            'subtotal', 'tax_total', 'discount_total', 'grand_total', 'updated_at',
        ])


class PurchaseOrderLine(TenantAwareModel, TimeStampedModel):
    po = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name='lines',
    )
    line_number = models.PositiveIntegerField(default=1)
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='purchase_order_lines',
        null=True, blank=True,
    )
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    unit_of_measure = models.CharField(max_length=20, default='EA')
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0'))],
    )
    tax_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    discount_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    required_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    line_subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    line_tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    line_discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    class Meta:
        ordering = ['po', 'line_number']
        unique_together = ('po', 'line_number')

    def __str__(self):
        return f'{self.po.po_number} L{self.line_number}'

    def save(self, *args, **kwargs):
        if not self.line_number_is_set():
            last = (
                PurchaseOrderLine.all_objects
                .filter(po=self.po).order_by('-line_number').first()
            )
            self.line_number = (last.line_number + 1) if last else 1
        # Compute denorm money columns.
        gross = (self.quantity or Decimal('0')) * (self.unit_price or Decimal('0'))
        disc = gross * (self.discount_pct or Decimal('0')) / Decimal('100')
        sub_after_disc = gross - disc
        tax = sub_after_disc * (self.tax_pct or Decimal('0')) / Decimal('100')
        total = sub_after_disc + tax
        self.line_subtotal = sub_after_disc.quantize(Decimal('0.01'))
        self.line_tax = tax.quantize(Decimal('0.01'))
        self.line_discount = disc.quantize(Decimal('0.01'))
        self.line_total = total.quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    def line_number_is_set(self):
        # `default=1` means a fresh row arrives with `line_number=1`; only treat
        # it as "set" if we are editing an existing row.
        return bool(self.pk)


class PurchaseOrderRevision(TenantAwareModel, TimeStampedModel):
    """Immutable JSON snapshot of a PO + lines captured on every Revise action.

    PROTECT FK per Lesson L-17 - audit-trail child must outlive its parent.
    """

    po = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name='revisions',
    )
    revision_number = models.PositiveIntegerField()
    change_summary = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='po_revisions',
    )
    snapshot_json = models.JSONField(default=dict)

    class Meta:
        ordering = ['po', '-revision_number']
        unique_together = ('po', 'revision_number')

    def __str__(self):
        return f'{self.po.po_number} rev {self.revision_number}'


class PurchaseOrderApproval(TenantAwareModel, TimeStampedModel):
    DECISION_CHOICES = [
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    po = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name='approvals',
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='po_approvals',
    )
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES)
    comments = models.TextField(blank=True)
    decided_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['po', '-decided_at']

    def __str__(self):
        return f'{self.po.po_number} {self.decision}'


# ============================================================================
# 9.2  SUPPLIER QUOTATION & RFQ
# ============================================================================

class RequestForQuotation(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('closed', 'Closed'),
        ('awarded', 'Awarded'),
        ('cancelled', 'Cancelled'),
    ]

    rfq_number = models.CharField(max_length=20)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    currency = models.CharField(max_length=3, default='USD')
    issued_date = models.DateField(null=True, blank=True)
    response_due_date = models.DateField(null=True, blank=True)
    round_number = models.PositiveIntegerField(default=1)
    parent_rfq = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='subsequent_rounds',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_rfqs',
    )

    class Meta:
        ordering = ['-id']
        unique_together = ('tenant', 'rfq_number')

    def __str__(self):
        return self.rfq_number

    def save(self, *args, **kwargs):
        if not self.rfq_number and self.tenant_id:
            last = (
                RequestForQuotation.all_objects
                .filter(tenant=self.tenant).order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.rfq_number = f'RFQ-{seq:05d}'
        super().save(*args, **kwargs)


class RFQLine(TenantAwareModel, TimeStampedModel):
    rfq = models.ForeignKey(
        RequestForQuotation, on_delete=models.CASCADE, related_name='lines',
    )
    line_number = models.PositiveIntegerField(default=1)
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='rfq_lines',
        null=True, blank=True,
    )
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    unit_of_measure = models.CharField(max_length=20, default='EA')
    target_price = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Internal target (hidden from suppliers).',
    )
    required_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['rfq', 'line_number']
        unique_together = ('rfq', 'line_number')

    def __str__(self):
        return f'{self.rfq.rfq_number} L{self.line_number}'

    def save(self, *args, **kwargs):
        if not self.pk:
            last = (
                RFQLine.all_objects.filter(rfq=self.rfq).order_by('-line_number').first()
            )
            self.line_number = (last.line_number + 1) if last else 1
        super().save(*args, **kwargs)


class RFQSupplier(TenantAwareModel, TimeStampedModel):
    PARTICIPATION_CHOICES = [
        ('invited', 'Invited'),
        ('quoted', 'Quoted'),
        ('declined', 'Declined'),
        ('no_response', 'No Response'),
    ]

    rfq = models.ForeignKey(
        RequestForQuotation, on_delete=models.CASCADE, related_name='invited_suppliers',
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='rfq_invitations',
    )
    invited_at = models.DateTimeField(default=timezone.now)
    responded_at = models.DateTimeField(null=True, blank=True)
    participation_status = models.CharField(
        max_length=20, choices=PARTICIPATION_CHOICES, default='invited',
    )

    class Meta:
        ordering = ['rfq', 'supplier']
        unique_together = ('rfq', 'supplier')

    def __str__(self):
        return f'{self.rfq.rfq_number} <- {self.supplier.code}'


class SupplierQuotation(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]

    quote_number = models.CharField(max_length=20)
    rfq = models.ForeignKey(
        RequestForQuotation, on_delete=models.PROTECT, related_name='quotations',
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='quotations',
    )
    quote_date = models.DateField(default=timezone.now)
    valid_until = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default='USD')
    payment_terms = models.CharField(max_length=60, blank=True)
    delivery_terms = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    notes = models.TextField(blank=True)

    subtotal = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    tax_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    grand_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )

    class Meta:
        ordering = ['-quote_date', '-id']
        unique_together = (
            ('tenant', 'quote_number'),
            ('rfq', 'supplier'),
        )

    def __str__(self):
        return self.quote_number

    def save(self, *args, **kwargs):
        if not self.quote_number and self.tenant_id:
            last = (
                SupplierQuotation.all_objects
                .filter(tenant=self.tenant).order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.quote_number = f'QUO-{seq:05d}'
        super().save(*args, **kwargs)

    def recompute_totals(self):
        agg = self.lines.aggregate(
            tot=models.Sum('quoted_subtotal'),
        )
        self.grand_total = agg['tot'] or Decimal('0')
        self.subtotal = self.grand_total
        self.save(update_fields=['subtotal', 'grand_total', 'updated_at'])


class QuotationLine(TenantAwareModel, TimeStampedModel):
    quotation = models.ForeignKey(
        SupplierQuotation, on_delete=models.CASCADE, related_name='lines',
    )
    rfq_line = models.ForeignKey(
        RFQLine, on_delete=models.PROTECT, related_name='quotation_lines',
    )
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0'))],
    )
    lead_time_days = models.PositiveIntegerField(
        default=0, validators=[MaxValueValidator(365)],
    )
    min_order_qty = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('1'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    comments = models.CharField(max_length=255, blank=True)

    quoted_subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    class Meta:
        ordering = ['quotation', 'rfq_line__line_number']
        unique_together = ('quotation', 'rfq_line')

    def __str__(self):
        return f'{self.quotation.quote_number} :: {self.rfq_line}'

    def save(self, *args, **kwargs):
        qty = self.rfq_line.quantity if self.rfq_line_id else Decimal('0')
        sub = (self.unit_price or Decimal('0')) * qty
        self.quoted_subtotal = sub.quantize(Decimal('0.01'))
        super().save(*args, **kwargs)


class QuotationAward(TenantAwareModel, TimeStampedModel):
    """One-to-one with RequestForQuotation. Records the award decision."""

    rfq = models.OneToOneField(
        RequestForQuotation, on_delete=models.CASCADE, related_name='award',
    )
    quotation = models.ForeignKey(
        SupplierQuotation, on_delete=models.PROTECT, related_name='awards',
    )
    awarded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rfq_awards',
    )
    awarded_at = models.DateTimeField(default=timezone.now)
    award_notes = models.TextField(blank=True)
    auto_create_po = models.BooleanField(
        default=True,
        help_text='If true, awarding the RFQ also drafts a PurchaseOrder.',
    )

    def __str__(self):
        return f'Award {self.rfq.rfq_number} -> {self.quotation.quote_number}'


# ============================================================================
# 9.3  SUPPLIER PERFORMANCE SCORECARD
# ============================================================================

class SupplierMetricEvent(TenantAwareModel, TimeStampedModel):
    """Append-only event log feeding scorecard math.

    Cross-module hooks emit rows automatically:
      - inventory.GoodsReceiptNote completion -> po_received_on_time / late
      - qms.IncomingInspection accept/reject -> quality_pass / fail
    """

    EVENT_CHOICES = [
        ('po_received_on_time', 'PO Received On Time'),
        ('po_received_late', 'PO Received Late'),
        ('quality_pass', 'Quality Pass'),
        ('quality_fail', 'Quality Fail'),
        ('price_variance', 'Price Variance'),
        ('response_received', 'Response Received'),
        ('response_missed', 'Response Missed'),
    ]

    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='metric_events',
    )
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)
    value = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal('0'),
        help_text='e.g. days late, defect %, price delta %',
    )
    posted_at = models.DateTimeField(default=timezone.now)
    reference_type = models.CharField(max_length=60, blank=True)
    reference_id = models.CharField(max_length=60, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-posted_at', '-id']
        indexes = [
            models.Index(fields=['tenant', 'supplier', '-posted_at']),
            models.Index(fields=['tenant', 'event_type', '-posted_at']),
        ]

    def __str__(self):
        return f'{self.supplier.code} {self.event_type} @ {self.posted_at:%Y-%m-%d}'


class SupplierScorecard(TenantAwareModel, TimeStampedModel):
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='scorecards',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    otd_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    quality_rating = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    price_variance_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('0'),
    )
    responsiveness_rating = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    defect_rate_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    total_pos = models.PositiveIntegerField(default=0)
    total_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    overall_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    rank = models.PositiveIntegerField(default=0)
    computed_at = models.DateTimeField(default=timezone.now)
    computed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='computed_scorecards',
    )

    class Meta:
        ordering = ['-period_end', 'rank']
        unique_together = ('tenant', 'supplier', 'period_start', 'period_end')

    def __str__(self):
        return f'{self.supplier.code} {self.period_start}..{self.period_end}'


# ============================================================================
# 9.4  SUPPLIER SELF-SERVICE PORTAL
# ============================================================================
#
# Auth model = apps.accounts.User with role='supplier' + supplier_company FK.
# Defined in apps.accounts.models; this module references the FK by string.

class SupplierASN(TenantAwareModel, TimeStampedModel):
    """Advance Shipping Notice. Suppliers post these via the portal."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('in_transit', 'In Transit'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]

    asn_number = models.CharField(max_length=20)
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name='asns',
    )
    ship_date = models.DateField(default=timezone.now)
    expected_arrival_date = models.DateField(null=True, blank=True)
    carrier = models.CharField(max_length=120, blank=True)
    tracking_number = models.CharField(max_length=120, blank=True)
    total_packages = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='submitted_asns',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='received_asns',
    )
    received_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-ship_date', '-id']
        unique_together = ('tenant', 'asn_number')

    def __str__(self):
        return self.asn_number

    def save(self, *args, **kwargs):
        if not self.asn_number and self.tenant_id:
            last = (
                SupplierASN.all_objects
                .filter(tenant=self.tenant).order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.asn_number = f'ASN-{seq:05d}'
        super().save(*args, **kwargs)


class SupplierASNLine(TenantAwareModel, TimeStampedModel):
    asn = models.ForeignKey(
        SupplierASN, on_delete=models.CASCADE, related_name='lines',
    )
    po_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.PROTECT, related_name='asn_lines',
    )
    quantity_shipped = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    lot_number = models.CharField(max_length=60, blank=True)
    serial_numbers = models.TextField(
        blank=True, help_text='Comma-separated serials.',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['asn', 'id']
        unique_together = ('asn', 'po_line')

    def __str__(self):
        return f'{self.asn.asn_number} :: PO line {self.po_line_id}'


def _supplier_invoice_upload(instance, filename):
    return f'procurement/invoices/{instance.tenant_id}/{filename}'


class SupplierInvoice(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected'),
        ('disputed', 'Disputed'),
    ]

    invoice_number = models.CharField(max_length=20)
    vendor_invoice_number = models.CharField(max_length=60)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='invoices',
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='supplier_invoices',
    )
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default='USD')

    subtotal = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    tax_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    grand_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    payment_reference = models.CharField(max_length=120, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='submitted_invoices',
    )
    attachment = models.FileField(
        upload_to=_supplier_invoice_upload, blank=True, null=True,
    )

    class Meta:
        ordering = ['-invoice_date', '-id']
        unique_together = (
            ('tenant', 'invoice_number'),
            ('supplier', 'vendor_invoice_number'),
        )

    def __str__(self):
        return self.invoice_number

    def save(self, *args, **kwargs):
        if not self.invoice_number and self.tenant_id:
            last = (
                SupplierInvoice.all_objects
                .filter(tenant=self.tenant).order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.invoice_number = f'SUPINV-{seq:05d}'
        super().save(*args, **kwargs)


class SupplierInvoiceLine(TenantAwareModel, TimeStampedModel):
    invoice = models.ForeignKey(
        SupplierInvoice, on_delete=models.CASCADE, related_name='lines',
    )
    line_number = models.PositiveIntegerField(default=1)
    po_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='invoice_lines',
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0'))],
    )
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    class Meta:
        ordering = ['invoice', 'line_number']
        unique_together = ('invoice', 'line_number')

    def __str__(self):
        return f'{self.invoice.invoice_number} L{self.line_number}'

    def save(self, *args, **kwargs):
        if not self.pk:
            last = (
                SupplierInvoiceLine.all_objects
                .filter(invoice=self.invoice).order_by('-line_number').first()
            )
            self.line_number = (last.line_number + 1) if last else 1
        gross = (self.quantity or Decimal('0')) * (self.unit_price or Decimal('0'))
        self.line_total = gross.quantize(Decimal('0.01'))
        super().save(*args, **kwargs)


# ============================================================================
# 9.5  BLANKET ORDERS & SCHEDULING AGREEMENTS
# ============================================================================

class BlanketOrder(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('closed', 'Closed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    bpo_number = models.CharField(max_length=20)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='blanket_orders',
    )
    start_date = models.DateField()
    end_date = models.DateField()
    currency = models.CharField(max_length=3, default='USD')
    total_committed_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    consumed_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_blanket_orders',
    )
    signed_at = models.DateTimeField(null=True, blank=True)
    signed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='signed_blanket_orders',
    )

    class Meta:
        ordering = ['-start_date', '-id']
        unique_together = ('tenant', 'bpo_number')

    def __str__(self):
        return self.bpo_number

    def save(self, *args, **kwargs):
        if not self.bpo_number and self.tenant_id:
            last = (
                BlanketOrder.all_objects
                .filter(tenant=self.tenant).order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.bpo_number = f'BPO-{seq:05d}'
        super().save(*args, **kwargs)

    @property
    def remaining_value(self):
        return self.total_committed_value - self.consumed_value


class BlanketOrderLine(TenantAwareModel, TimeStampedModel):
    blanket_order = models.ForeignKey(
        BlanketOrder, on_delete=models.CASCADE, related_name='lines',
    )
    line_number = models.PositiveIntegerField(default=1)
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='blanket_lines',
    )
    description = models.CharField(max_length=255, blank=True)
    total_quantity = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    consumed_quantity = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    unit_of_measure = models.CharField(max_length=20, default='EA')
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0'))],
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['blanket_order', 'line_number']
        unique_together = ('blanket_order', 'line_number')

    def __str__(self):
        return f'{self.blanket_order.bpo_number} L{self.line_number}'

    def save(self, *args, **kwargs):
        if not self.pk:
            last = (
                BlanketOrderLine.all_objects
                .filter(blanket_order=self.blanket_order).order_by('-line_number').first()
            )
            self.line_number = (last.line_number + 1) if last else 1
        super().save(*args, **kwargs)

    @property
    def remaining_quantity(self):
        return self.total_quantity - self.consumed_quantity


class ScheduleRelease(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('released', 'Released'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]

    release_number = models.CharField(max_length=20)
    blanket_order = models.ForeignKey(
        BlanketOrder, on_delete=models.PROTECT, related_name='releases',
    )
    release_date = models.DateField(default=timezone.now)
    required_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='source_releases',
    )
    total_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_releases',
    )

    class Meta:
        ordering = ['-release_date', '-id']
        unique_together = ('tenant', 'release_number')

    def __str__(self):
        return self.release_number

    def save(self, *args, **kwargs):
        if not self.release_number and self.tenant_id:
            last = (
                ScheduleRelease.all_objects
                .filter(tenant=self.tenant).order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.release_number = f'REL-{seq:05d}'
        super().save(*args, **kwargs)

    def recompute_total(self):
        agg = self.lines.aggregate(
            tot=models.Sum('line_total'),
        )
        self.total_amount = agg['tot'] or Decimal('0')
        self.save(update_fields=['total_amount', 'updated_at'])


class ScheduleReleaseLine(TenantAwareModel, TimeStampedModel):
    release = models.ForeignKey(
        ScheduleRelease, on_delete=models.CASCADE, related_name='lines',
    )
    blanket_order_line = models.ForeignKey(
        BlanketOrderLine, on_delete=models.PROTECT, related_name='release_lines',
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    required_date = models.DateField(null=True, blank=True)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    class Meta:
        ordering = ['release', 'id']
        unique_together = ('release', 'blanket_order_line')

    def __str__(self):
        return f'{self.release.release_number} :: BL{self.blanket_order_line_id}'

    def save(self, *args, **kwargs):
        unit = self.blanket_order_line.unit_price if self.blanket_order_line_id else Decimal('0')
        self.line_total = ((self.quantity or Decimal('0')) * unit).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)
