"""Module 1 — Tenant & Subscription Management.

Contains: Plan, Subscription, Invoice, Payment, BillingAddress, UsageMeter,
BrandingSettings, EmailTemplate, TenantAuditLog, TenantHealthSnapshot, HealthAlert.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Tenant, TenantAwareModel, TimeStampedModel


# -------------------- Plans & Subscriptions --------------------

class Plan(TimeStampedModel):
    """Subscription plan offered to tenants. NOT tenant-scoped (shared catalog)."""

    INTERVAL_MONTHLY = 'monthly'
    INTERVAL_YEARLY = 'yearly'

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    price_yearly = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=3, default='USD')
    trial_days = models.PositiveIntegerField(default=14)
    features = models.JSONField(default=list, blank=True)
    max_users = models.PositiveIntegerField(default=10)
    max_production_orders = models.PositiveIntegerField(default=1000)
    max_storage_mb = models.PositiveIntegerField(default=1024)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'price_monthly']

    def __str__(self):
        return self.name


class Subscription(TimeStampedModel):
    STATUS_CHOICES = [
        ('trial', 'Trial'),
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('cancelled', 'Cancelled'),
        ('paused', 'Paused'),
    ]
    INTERVAL_CHOICES = [
        (Plan.INTERVAL_MONTHLY, 'Monthly'),
        (Plan.INTERVAL_YEARLY, 'Yearly'),
    ]

    tenant = models.OneToOneField(
        Tenant, on_delete=models.CASCADE, related_name='subscription',
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='subscriptions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trial')
    interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES, default=Plan.INTERVAL_MONTHLY)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField()
    cancel_at_period_end = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    gateway_subscription_id = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return f'{self.tenant} · {self.plan} ({self.status})'

    @property
    def price(self):
        return self.plan.price_yearly if self.interval == Plan.INTERVAL_YEARLY else self.plan.price_monthly

    @property
    def is_active(self):
        return self.status in ('trial', 'active')


class BillingAddress(TenantAwareModel, TimeStampedModel):
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100)
    tax_id = models.CharField(max_length=60, blank=True)

    def __str__(self):
        return f'{self.line1}, {self.city}'


# -------------------- Invoices & Payments --------------------

class Invoice(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('open', 'Open'),
        ('paid', 'Paid'),
        ('void', 'Void'),
        ('uncollectible', 'Uncollectible'),
    ]

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name='invoices', null=True, blank=True,
    )
    number = models.CharField(max_length=30, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default='USD')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField(blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-issue_date', '-id']

    def __str__(self):
        return self.number


class InvoiceLineItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='line_items')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    def save(self, *args, **kwargs):
        self.amount = (self.quantity or Decimal('0')) * (self.unit_price or Decimal('0'))
        super().save(*args, **kwargs)


class Payment(TenantAwareModel, TimeStampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('succeeded', 'Succeeded'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    METHOD_CHOICES = [
        ('card', 'Card'),
        ('bank', 'Bank Transfer'),
        ('wallet', 'Wallet'),
        ('manual', 'Manual'),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    gateway = models.CharField(max_length=30, default='mock')
    gateway_ref = models.CharField(max_length=120, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='card')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Payment {self.gateway_ref or self.pk} ({self.status})'


# -------------------- Usage metering --------------------

class UsageMeter(TenantAwareModel, TimeStampedModel):
    """Tracks tenant consumption per billing period (for usage-based billing)."""

    METRIC_CHOICES = [
        ('users', 'Active Users'),
        ('production_orders', 'Production Orders'),
        ('storage_mb', 'Storage MB'),
        ('api_calls', 'API Calls'),
    ]

    metric = models.CharField(max_length=30, choices=METRIC_CHOICES)
    period_start = models.DateField()
    period_end = models.DateField()
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))

    class Meta:
        unique_together = ('tenant', 'metric', 'period_start')


# -------------------- Branding --------------------

class BrandingSettings(TimeStampedModel):
    """Per-tenant white-label settings. OneToOne to Tenant."""

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='branding')
    logo_light = models.ImageField(upload_to='branding/logos/', blank=True, null=True)
    logo_dark = models.ImageField(upload_to='branding/logos/', blank=True, null=True)
    favicon = models.ImageField(upload_to='branding/favicons/', blank=True, null=True)
    primary_color = models.CharField(max_length=9, default='#3b5de7')
    secondary_color = models.CharField(max_length=9, default='#6c757d')
    sidebar_color = models.CharField(max_length=9, default='#ffffff')
    topbar_color = models.CharField(max_length=9, default='#ffffff')
    email_from_name = models.CharField(max_length=120, blank=True)
    email_from_address = models.EmailField(blank=True)
    footer_text = models.CharField(max_length=255, blank=True)
    support_email = models.EmailField(blank=True)
    support_url = models.URLField(blank=True)
    # WARNING: do NOT log this value. Reference only — raw keys live in a secrets manager.
    encryption_key_ref = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f'Branding · {self.tenant}'


class EmailTemplate(TenantAwareModel, TimeStampedModel):
    CODE_CHOICES = [
        ('welcome', 'Welcome'),
        ('invite', 'User Invite'),
        ('password_reset', 'Password Reset'),
        ('invoice_issued', 'Invoice Issued'),
        ('payment_received', 'Payment Received'),
        ('subscription_cancelled', 'Subscription Cancelled'),
        ('trial_ending', 'Trial Ending'),
    ]

    code = models.CharField(max_length=40, choices=CODE_CHOICES)
    subject = models.CharField(max_length=255)
    html_body = models.TextField()
    text_body = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f'{self.code} · {self.tenant}'


# -------------------- Audit log --------------------

class TenantAuditLog(TenantAwareModel):
    """Immutable log of tenant-level actions."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_logs',
    )
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=80, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['tenant', '-timestamp']),
            models.Index(fields=['action']),
        ]

    def __str__(self):
        return f'{self.action} @ {self.timestamp:%Y-%m-%d %H:%M}'


# -------------------- Health monitoring --------------------

class TenantHealthSnapshot(TenantAwareModel):
    captured_at = models.DateTimeField(default=timezone.now)
    active_users = models.PositiveIntegerField(default=0)
    storage_mb = models.PositiveIntegerField(default=0)
    api_calls_24h = models.PositiveIntegerField(default=0)
    error_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    avg_response_ms = models.PositiveIntegerField(default=0)
    health_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('100.00'))

    class Meta:
        ordering = ['-captured_at']
        indexes = [models.Index(fields=['tenant', '-captured_at'])]

    def __str__(self):
        return f'Health {self.tenant} @ {self.captured_at:%Y-%m-%d}'


class HealthAlert(TenantAwareModel, TimeStampedModel):
    KIND_CHOICES = [
        ('error_rate', 'Error Rate'),
        ('response_time', 'Response Time'),
        ('storage', 'Storage'),
        ('api_quota', 'API Quota'),
    ]
    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('webhook', 'Webhook'),
        ('in_app', 'In-App'),
    ]

    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    threshold = models.DecimalField(max_digits=10, decimal_places=2)
    triggered_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='in_app')
    message = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.kind} @ {self.threshold}'
