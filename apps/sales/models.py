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
