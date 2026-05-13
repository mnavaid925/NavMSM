"""Module 17 - Sales & Customer Order Management.

Sub-modules:
    17.1  Customer Master & CRM Lite
            (CustomerCategory, PriceList, PriceListItem, Customer,
             CustomerContact, CommunicationLog, CustomerDocument)
    17.2  Sales Order Processing                       (added in 17.2 turn)
    17.3  Order Promising & ATP/CTP                    (added in 17.3 turn)
    17.4  Delivery Scheduling & Dispatch + Invoicing   (added in 17.4 turn)
    17.5  Customer Portal                              (FK on accounts.User)

Cross-module integration (added in later turns):
    - apps.pps.ProductionOrder.source_sales_line  (added 17.2; MTO auto-PO)
    - apps.inventory.StockMovement.source_shipment (added 17.4; emission key)
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel, TimeStampedModel


# ============================================================================
# 17.1  CUSTOMER MASTER & CRM LITE
# ============================================================================

class CustomerCategory(TenantAwareModel, TimeStampedModel):
    """Hierarchical lookup for customer industry / segment / region.

    Self-referencing FK supports trees like:
        Industry > Manufacturing > Automotive > Tier-1
    """

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, blank=True)
    parent = models.ForeignKey(
        'self', on_delete=models.PROTECT,
        null=True, blank=True, related_name='children',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'name', 'parent')
        verbose_name_plural = 'Customer categories'

    def __str__(self):
        return self.name


class PriceList(TenantAwareModel, TimeStampedModel):
    """Header for a sellable price book (currency + effective window).

    `is_default=True` marks the tenant-wide fallback price list used by
    `services/pricing.resolve_price` when a customer has no
    `default_price_list` of their own.
    """

    code = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=120)
    currency = models.CharField(max_length=3, default='USD')
    effective_from = models.DateField(default=timezone.now)
    effective_to = models.DateField(null=True, blank=True)
    is_default = models.BooleanField(
        default=False,
        help_text='Tenant-wide fallback when a customer has no price list set.',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-is_default', 'name']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code or self.name}'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            last = (
                PriceList.all_objects.filter(tenant=self.tenant)
                .order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.code = f'PL-{seq:05d}'
        super().save(*args, **kwargs)


class PriceListItem(TenantAwareModel, TimeStampedModel):
    """Row in a price list: per-product tiered price + optional discount."""

    price_list = models.ForeignKey(
        PriceList, on_delete=models.CASCADE, related_name='items',
    )
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='sales_price_items',
    )
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0'))],
    )
    min_qty = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('1'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Tier break - this row applies when ordered qty >= min_qty.',
    )
    discount_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['price_list', 'product', 'min_qty']
        unique_together = ('price_list', 'product', 'min_qty')

    def __str__(self):
        return f'{self.product} @ {self.unit_price} (>= {self.min_qty})'


class Customer(TenantAwareModel, TimeStampedModel):
    """Sold-to entity. The root of CRM, sales orders, shipments, invoices."""

    CUSTOMER_CLASS_CHOICES = [
        ('key', 'Key Account'),
        ('standard', 'Standard'),
        ('distributor', 'Distributor / Reseller'),
        ('one_time', 'One-time / Walk-in'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('on_hold', 'On Hold'),
        ('blacklisted', 'Blacklisted'),
    ]
    PAYMENT_TERMS_CHOICES = [
        ('cod', 'Cash on Delivery'),
        ('prepaid', 'Prepaid'),
        ('net15', 'Net 15'),
        ('net30', 'Net 30'),
        ('net45', 'Net 45'),
        ('net60', 'Net 60'),
        ('net90', 'Net 90'),
    ]

    code = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=200, blank=True)
    customer_class = models.CharField(
        max_length=20, choices=CUSTOMER_CLASS_CHOICES, default='standard',
    )
    category = models.ForeignKey(
        CustomerCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='customers',
    )

    # Contact / address (sold-to copy; ship-to overrides live on the order)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    website = models.URLField(blank=True)
    tax_id = models.CharField(max_length=60, blank=True)
    billing_address = models.TextField(blank=True)
    shipping_address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True)

    # Commercial defaults
    currency = models.CharField(max_length=3, default='USD')
    payment_terms = models.CharField(
        max_length=20, choices=PAYMENT_TERMS_CHOICES, default='net30',
    )
    credit_limit = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Hard cap on total open AR + unfulfilled orders.',
    )
    credit_used = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        help_text='Denormalised running total. Recompute via management command.',
    )
    default_price_list = models.ForeignKey(
        PriceList, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='default_for_customers',
    )
    default_warehouse = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='default_for_customers',
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    risk_flag = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}' if self.code else self.name

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            last = (
                Customer.all_objects.filter(tenant=self.tenant)
                .order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.code = f'CUST-{seq:05d}'
        super().save(*args, **kwargs)

    @property
    def credit_available(self) -> Decimal:
        return (self.credit_limit or Decimal('0')) - (self.credit_used or Decimal('0'))


class CustomerContact(TenantAwareModel, TimeStampedModel):
    """One contact person for a customer (multiple per customer allowed)."""

    ROLE_CHOICES = [
        ('buyer', 'Buyer / Purchasing'),
        ('accounts', 'Accounts Payable'),
        ('shipping', 'Receiving / Logistics'),
        ('technical', 'Technical / Engineering'),
        ('executive', 'Executive'),
        ('other', 'Other'),
    ]

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name='contacts',
    )
    full_name = models.CharField(max_length=120)
    designation = models.CharField(max_length=80, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='buyer')
    email = models.EmailField(blank=True)
    phone_primary = models.CharField(max_length=30, blank=True)
    phone_alt = models.CharField(max_length=30, blank=True)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['customer', '-is_primary', 'full_name']

    def __str__(self):
        return f'{self.full_name} ({self.customer.name})'


class CommunicationLog(TenantAwareModel, TimeStampedModel):
    """Append-only call / email / meeting / note log against a customer.

    The Edit / Delete actions are restricted to rows < 24h old (enforced
    at the view layer). This mirrors `procurement.SupplierMetricEvent`.
    """

    TYPE_CHOICES = [
        ('call', 'Phone Call'),
        ('email', 'Email'),
        ('meeting', 'Meeting'),
        ('note', 'Note'),
        ('sms', 'SMS / Text'),
    ]
    DIRECTION_CHOICES = [
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
        ('internal', 'Internal'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ]

    code = models.CharField(max_length=20, blank=True)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name='communications',
    )
    contact = models.ForeignKey(
        CustomerContact, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='communications',
    )
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='note')
    direction = models.CharField(
        max_length=10, choices=DIRECTION_CHOICES, default='outbound',
    )
    subject = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    follow_up_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='done')
    # Reverse-FK to sales order added in 17.2 - kept nullable here so the
    # migration is forward-compatible.
    related_order_id = models.PositiveBigIntegerField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_sales_communications',
    )

    class Meta:
        ordering = ['-occurred_at', '-id']

    def __str__(self):
        return f'{self.code or "(new)"} - {self.subject}'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            last = (
                CommunicationLog.all_objects.filter(tenant=self.tenant)
                .order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.code = f'COMM-{seq:05d}'
        super().save(*args, **kwargs)

    def is_locked(self) -> bool:
        """Return True once the row is older than 24h (no edit / delete)."""
        if not self.pk or not self.created_at:
            return False
        return (timezone.now() - self.created_at).total_seconds() > 24 * 3600


def _validate_customer_doc(file):
    """File-upload validator: 25 MB cap + extension allowlist (L-22)."""
    from django.core.exceptions import ValidationError
    max_bytes = 25 * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError('File exceeds 25 MB limit.')
    allowed = {'.pdf', '.png', '.jpg', '.jpeg', '.docx'}
    name = (file.name or '').lower()
    if not any(name.endswith(ext) for ext in allowed):
        raise ValidationError(
            'Allowed file types: PDF, PNG, JPG, JPEG, DOCX.',
        )


class CustomerDocument(TenantAwareModel, TimeStampedModel):
    """Attachment slot for NDAs / MSAs / contracts / certificates."""

    DOC_TYPE_CHOICES = [
        ('nda', 'NDA'),
        ('msa', 'Master Service Agreement'),
        ('contract', 'Contract'),
        ('certificate', 'Certificate'),
        ('other', 'Other'),
    ]

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name='documents',
    )
    doc_type = models.CharField(
        max_length=20, choices=DOC_TYPE_CHOICES, default='contract',
    )
    title = models.CharField(max_length=200)
    file = models.FileField(
        upload_to='sales/customer-docs/%Y/%m/',
        validators=[_validate_customer_doc],
    )
    expires_at = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='uploaded_customer_documents',
    )

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.title} ({self.customer.name})'


# ============================================================================
# 17.2  SALES ORDER PROCESSING
# ============================================================================

class SalesOrder(TenantAwareModel, TimeStampedModel):
    """Customer purchase order accepted by us.

    Workflow:  draft -> submitted -> credit_check -> confirmed -> in_production
                -> fulfilled -> invoiced -> closed  (plus cancelled / on_hold).
    The submitted -> credit_check / confirmed branch is driven by the credit
    service in `apps/sales/services/credit.py`.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('credit_check', 'Credit Check'),
        ('confirmed', 'Confirmed'),
        ('in_production', 'In Production'),
        ('fulfilled', 'Fulfilled'),
        ('invoiced', 'Invoiced'),
        ('closed', 'Closed'),
        ('on_hold', 'On Hold'),
        ('cancelled', 'Cancelled'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('rush', 'Rush'),
    ]

    code = models.CharField(max_length=20, blank=True)
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name='sales_orders',
    )
    customer_po_number = models.CharField(
        max_length=60, blank=True,
        help_text='The customer-supplied PO reference (free text).',
    )
    order_date = models.DateField(default=timezone.now)
    requested_delivery_date = models.DateField(null=True, blank=True)
    promised_delivery_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    credit_hold = models.BooleanField(
        default=False,
        help_text='Set automatically by the credit service when the customer '
                  'fails a credit check. Manual override allowed.',
    )

    currency = models.CharField(max_length=3, default='USD')
    payment_terms = models.CharField(
        max_length=20, choices=Customer.PAYMENT_TERMS_CHOICES, default='net30',
    )
    source_warehouse = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sales_orders',
    )
    sales_rep = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sales_orders_as_rep',
    )

    # Address snapshot at time of order (customer addresses can change later)
    billing_address = models.TextField(blank=True)
    shipping_address = models.TextField(blank=True)

    # Denorm totals - kept fresh by recompute_totals()
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    shipping_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_sales_orders',
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='confirmed_sales_orders',
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-order_date', '-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'(draft SO #{self.pk})'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            last = (
                SalesOrder.all_objects.filter(tenant=self.tenant)
                .order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.code = f'SO-{seq:05d}'
        super().save(*args, **kwargs)

    def is_editable(self):
        return self.status in ('draft', 'on_hold')

    def can_submit(self):
        return self.status == 'draft'

    def can_confirm(self):
        return self.status in ('submitted', 'credit_check') and not self.credit_hold

    def can_cancel(self):
        return self.status not in ('fulfilled', 'invoiced', 'closed', 'cancelled')

    def can_revise(self):
        return self.status in ('confirmed', 'in_production')

    def recompute_totals(self):
        agg = self.lines.aggregate(
            sub=models.Sum('line_total'),
            disc=models.Sum('line_discount'),
            tax=models.Sum('line_tax'),
        )
        self.subtotal = (agg['sub'] or Decimal('0')) + (agg['disc'] or Decimal('0'))
        self.discount_total = agg['disc'] or Decimal('0')
        self.tax_total = agg['tax'] or Decimal('0')
        line_total_sum = agg['sub'] or Decimal('0')
        self.grand_total = line_total_sum + self.tax_total + (self.shipping_total or Decimal('0'))
        self.save(update_fields=[
            'subtotal', 'discount_total', 'tax_total',
            'grand_total', 'updated_at',
        ])


class SalesOrderLine(TenantAwareModel, TimeStampedModel):
    """One product line on a sales order."""

    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.CASCADE, related_name='lines',
    )
    line_no = models.PositiveIntegerField(default=1)
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='sales_order_lines',
    )
    description = models.CharField(max_length=255, blank=True)
    unit_of_measure = models.CharField(max_length=20, default='EA')

    qty_ordered = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    # Denorm progress columns (updated by promising/shipping/invoicing flows)
    qty_promised = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    qty_shipped = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    qty_invoiced = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))

    unit_price = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0'))],
    )
    line_discount_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    line_tax_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )

    # Denorm money columns - recomputed in save()
    line_discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    line_tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    requested_date = models.DateField(null=True, blank=True)
    promised_date = models.DateField(null=True, blank=True)

    is_make_to_order = models.BooleanField(
        default=False,
        help_text='When True, confirming the parent SO will auto-draft a '
                  'pps.ProductionOrder for this line.',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['sales_order', 'line_no']
        unique_together = ('sales_order', 'line_no')

    def __str__(self):
        return f'{self.sales_order.code} L{self.line_no}'

    def save(self, *args, **kwargs):
        # Auto-assign line_no within parent SO
        if not self.line_no or self.line_no == 1:
            existing = (
                SalesOrderLine.all_objects.filter(sales_order=self.sales_order)
                .exclude(pk=self.pk).order_by('-line_no').first()
            )
            if existing:
                self.line_no = existing.line_no + 1
        # Compute denorm money columns
        gross = (self.qty_ordered or Decimal('0')) * (self.unit_price or Decimal('0'))
        self.line_discount = (gross * (self.line_discount_pct or Decimal('0')) / Decimal('100')).quantize(Decimal('0.01'))
        sub_after_disc = gross - self.line_discount
        self.line_tax = (sub_after_disc * (self.line_tax_pct or Decimal('0')) / Decimal('100')).quantize(Decimal('0.01'))
        self.line_total = (sub_after_disc).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)


class SalesOrderRevision(TenantAwareModel, TimeStampedModel):
    """Immutable snapshot of an SO header + lines taken on every Revise action.

    Mirrors `procurement.PurchaseOrderRevision`.
    """

    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.CASCADE, related_name='revisions',
    )
    version_no = models.PositiveIntegerField()
    snapshot_json = models.JSONField(default=dict, blank=True)
    revised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sales_order_revisions',
    )
    revised_at = models.DateTimeField(default=timezone.now)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ['sales_order', '-version_no']
        unique_together = ('sales_order', 'version_no')

    def __str__(self):
        return f'{self.sales_order.code} rev v{self.version_no}'


class SalesOrderApprovalLog(TenantAwareModel, TimeStampedModel):
    """Append-only workflow audit trail for SalesOrder transitions."""

    ACTION_CHOICES = [
        ('submit', 'Submit'),
        ('credit_release', 'Credit Release'),
        ('credit_hold', 'Credit Hold'),
        ('confirm', 'Confirm'),
        ('cancel', 'Cancel'),
        ('hold', 'Hold'),
        ('resume', 'Resume'),
        ('revise', 'Revise'),
    ]

    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.CASCADE, related_name='approval_logs',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sales_order_actions',
    )
    performed_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-performed_at', '-id']

    def __str__(self):
        return f'{self.sales_order.code} {self.action} {self.from_status}->{self.to_status}'


# ============================================================================
# 17.3  ORDER PROMISING & ATP / CTP
# ============================================================================

class ATPCalculation(TenantAwareModel, TimeStampedModel):
    """Available-to-Promise calculation snapshot. Pure-read - never mutates stock."""

    METHOD_CHOICES = [
        ('stock_only', 'On-hand stock only'),
        ('stock_plus_open_po', 'On-hand + open PO arrivals'),
        ('stock_plus_pps', 'On-hand + planned PPS production'),
    ]
    RESULT_CHOICES = [
        ('fully_promised', 'Fully Promised'),
        ('partially_promised', 'Partially Promised'),
        ('no_stock', 'No Stock'),
    ]

    code = models.CharField(max_length=20, blank=True)
    order_line = models.ForeignKey(
        SalesOrderLine, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='atp_calculations',
    )
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='atp_calculations',
    )
    requested_qty = models.DecimalField(max_digits=14, decimal_places=4)
    requested_date = models.DateField()
    method = models.CharField(max_length=30, choices=METHOD_CHOICES, default='stock_plus_open_po')

    available_qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    available_date = models.DateField(null=True, blank=True)
    result_status = models.CharField(max_length=30, choices=RESULT_CHOICES, default='no_stock')

    snapshot_json = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(default=timezone.now)
    computed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='atp_calculations',
    )

    class Meta:
        ordering = ['-computed_at', '-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code or "ATP"} {self.product} x{self.requested_qty}'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            last = (
                ATPCalculation.all_objects.filter(tenant=self.tenant)
                .order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.code = f'ATP-{seq:05d}'
        super().save(*args, **kwargs)


class CTPCalculation(TenantAwareModel, TimeStampedModel):
    """Capable-to-Promise calculation: for an ATP shortfall, walks BOM + capacity
    to determine the earliest realistic completion date. Pure read."""

    code = models.CharField(max_length=20, blank=True)
    order_line = models.ForeignKey(
        SalesOrderLine, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ctp_calculations',
    )
    product = models.ForeignKey(
        'plm.Product', on_delete=models.PROTECT, related_name='ctp_calculations',
    )
    shortfall_qty = models.DecimalField(max_digits=14, decimal_places=4)
    target_date = models.DateField()

    capable_qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    earliest_completion_date = models.DateField(null=True, blank=True)
    bottleneck_work_center = models.ForeignKey(
        'pps.WorkCenter', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ctp_bottlenecks',
    )

    simulation_json = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(default=timezone.now)
    computed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ctp_calculations',
    )

    class Meta:
        ordering = ['-computed_at', '-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code or "CTP"} {self.product} shortfall={self.shortfall_qty}'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            last = (
                CTPCalculation.all_objects.filter(tenant=self.tenant)
                .order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.code = f'CTP-{seq:05d}'
        super().save(*args, **kwargs)


class OrderPromise(TenantAwareModel, TimeStampedModel):
    """Denormalised order-line promise. 1-to-1 with SalesOrderLine."""

    TYPE_CHOICES = [
        ('stock', 'From Stock'),
        ('production', 'From New Production'),
        ('mixed', 'Mixed (Stock + Production)'),
        ('partial', 'Partial'),
        ('unfulfillable', 'Unfulfillable'),
    ]

    order_line = models.OneToOneField(
        SalesOrderLine, on_delete=models.CASCADE, related_name='promise',
    )
    promise_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='stock')
    promised_qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    promised_date = models.DateField(null=True, blank=True)
    atp_ref = models.ForeignKey(
        ATPCalculation, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='promises',
    )
    ctp_ref = models.ForeignKey(
        CTPCalculation, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='promises',
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='confirmed_promises',
    )

    class Meta:
        ordering = ['-confirmed_at', '-id']

    def __str__(self):
        return f'Promise {self.order_line} ({self.get_promise_type_display()})'


# ============================================================================
# 17.4  DELIVERY SCHEDULING & DISPATCH + SALES INVOICING
# ============================================================================

class DeliveryRoute(TenantAwareModel, TimeStampedModel):
    """Logical grouping of shipments dispatched on a single route."""

    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('dispatched', 'Dispatched'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    code = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=120)
    route_date = models.DateField(default=timezone.now)
    driver_name = models.CharField(max_length=120, blank=True)
    vehicle_no = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    total_stops = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-route_date', '-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} - {self.name}' if self.code else self.name

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            last = (
                DeliveryRoute.all_objects.filter(tenant=self.tenant)
                .order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.code = f'ROUTE-{seq:05d}'
        super().save(*args, **kwargs)


class Shipment(TenantAwareModel, TimeStampedModel):
    """Outbound delivery of one sales order's lines.

    Workflow: planned -> picked -> packed -> in_transit -> delivered
              (plus returned / cancelled).

    `status='delivered'` emits one inventory.StockMovement per ShipmentLine
    via post_save signal (idempotent on `source_shipment` FK).
    """

    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('picked', 'Picked'),
        ('packed', 'Packed'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('returned', 'Returned'),
        ('cancelled', 'Cancelled'),
    ]

    code = models.CharField(max_length=20, blank=True)
    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.PROTECT, related_name='shipments',
    )
    route = models.ForeignKey(
        DeliveryRoute, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='shipments',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    source_warehouse = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='outbound_shipments',
    )
    carrier_name = models.CharField(max_length=120, blank=True)
    tracking_number = models.CharField(max_length=120, blank=True)
    weight_kg = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    volume_m3 = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    planned_ship_date = models.DateField(null=True, blank=True)
    actual_ship_date = models.DateField(null=True, blank=True)
    expected_delivery_date = models.DateField(null=True, blank=True)
    actual_delivery_date = models.DateField(null=True, blank=True)
    freight_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    insurance_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_shipments',
    )

    class Meta:
        ordering = ['-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'(new shipment #{self.pk})'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            last = (
                Shipment.all_objects.filter(tenant=self.tenant)
                .order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.code = f'SHP-{seq:05d}'
        super().save(*args, **kwargs)

    def is_editable(self):
        return self.status in ('planned', 'picked')

    def can_pick(self):
        return self.status == 'planned'

    def can_pack(self):
        return self.status == 'picked'

    def can_dispatch(self):
        return self.status == 'packed'

    def can_deliver(self):
        return self.status == 'in_transit'

    def can_cancel(self):
        return self.status not in ('delivered', 'returned', 'cancelled')


class ShipmentLine(TenantAwareModel, TimeStampedModel):
    """One picked line in a Shipment, tied to a SalesOrderLine."""

    PICK_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('picked', 'Picked'),
        ('packed', 'Packed'),
    ]

    shipment = models.ForeignKey(
        Shipment, on_delete=models.CASCADE, related_name='shipment_lines',
    )
    order_line = models.ForeignKey(
        SalesOrderLine, on_delete=models.PROTECT, related_name='shipment_lines',
    )
    qty_to_ship = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    qty_shipped = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'),
    )
    lot_no = models.CharField(max_length=60, blank=True)
    serial_no = models.CharField(max_length=120, blank=True)
    source_bin = models.ForeignKey(
        'inventory.StorageBin', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='outbound_shipment_lines',
    )
    pick_status = models.CharField(
        max_length=20, choices=PICK_STATUS_CHOICES, default='pending',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['shipment', 'id']

    def __str__(self):
        return f'{self.shipment.code} L{self.pk}'


class ProofOfDelivery(TenantAwareModel, TimeStampedModel):
    """Proof-of-delivery artefact captured at the delivery moment."""

    code = models.CharField(max_length=20, blank=True)
    shipment = models.OneToOneField(
        Shipment, on_delete=models.CASCADE, related_name='pod',
    )
    delivered_at = models.DateTimeField(default=timezone.now)
    received_by_name = models.CharField(max_length=120, blank=True)
    received_by_signature = models.FileField(
        upload_to='sales/pod/signatures/%Y/%m/',
        null=True, blank=True,
    )
    photo_attachment = models.FileField(
        upload_to='sales/pod/photos/%Y/%m/',
        null=True, blank=True,
    )
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='recorded_pods',
    )

    class Meta:
        ordering = ['-delivered_at']

    def __str__(self):
        return self.code or f'POD shipment #{self.shipment_id}'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            last = (
                ProofOfDelivery.all_objects.filter(tenant=self.tenant)
                .order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.code = f'POD-{seq:05d}'
        super().save(*args, **kwargs)


class SalesInvoice(TenantAwareModel, TimeStampedModel):
    """Customer invoice issued for a SalesOrder. Supports partial and
    consolidated invoicing via the nullable `shipment` FK."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    code = models.CharField(max_length=20, blank=True)
    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.PROTECT, related_name='invoices',
    )
    shipment = models.ForeignKey(
        Shipment, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='invoices',
    )
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    payment_terms = models.CharField(
        max_length=20, choices=Customer.PAYMENT_TERMS_CHOICES, default='net30',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    shipping_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    notes = models.TextField(blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='issued_sales_invoices',
    )

    class Meta:
        ordering = ['-invoice_date', '-id']
        unique_together = ('tenant', 'code')

    def __str__(self):
        return self.code or f'(draft SINV #{self.pk})'

    def save(self, *args, **kwargs):
        if not self.code and self.tenant_id:
            last = (
                SalesInvoice.all_objects.filter(tenant=self.tenant)
                .order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            self.code = f'SINV-{seq:05d}'
        super().save(*args, **kwargs)

    def recompute_totals(self):
        agg = self.lines.aggregate(
            sub=models.Sum('line_total'),
            disc=models.Sum('line_discount'),
            tax=models.Sum('line_tax'),
        )
        self.discount_total = agg['disc'] or Decimal('0')
        self.tax_total = agg['tax'] or Decimal('0')
        line_total_sum = agg['sub'] or Decimal('0')
        self.subtotal = line_total_sum + self.discount_total
        self.grand_total = line_total_sum + self.tax_total + (self.shipping_total or Decimal('0'))
        self.save(update_fields=[
            'subtotal', 'tax_total', 'discount_total',
            'grand_total', 'updated_at',
        ])


class SalesInvoiceLine(TenantAwareModel, TimeStampedModel):
    """One billable line on a SalesInvoice."""

    invoice = models.ForeignKey(
        SalesInvoice, on_delete=models.CASCADE, related_name='lines',
    )
    shipment_line = models.ForeignKey(
        ShipmentLine, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='invoice_lines',
    )
    description = models.CharField(max_length=255)
    qty = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=4,
        validators=[MinValueValidator(Decimal('0'))],
    )
    line_discount_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    line_tax_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
    )
    line_discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    line_tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    class Meta:
        ordering = ['invoice', 'id']

    def __str__(self):
        return f'{self.invoice.code} - {self.description}'

    def save(self, *args, **kwargs):
        gross = (self.qty or Decimal('0')) * (self.unit_price or Decimal('0'))
        self.line_discount = (gross * (self.line_discount_pct or Decimal('0')) / Decimal('100')).quantize(Decimal('0.01'))
        sub_after = gross - self.line_discount
        self.line_tax = (sub_after * (self.line_tax_pct or Decimal('0')) / Decimal('100')).quantize(Decimal('0.01'))
        self.line_total = sub_after.quantize(Decimal('0.01'))
        super().save(*args, **kwargs)
