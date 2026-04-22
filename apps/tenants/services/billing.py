"""Billing / subscription / invoice helpers."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.models import Tenant

from ..models import (
    BrandingSettings, EmailTemplate, Invoice, InvoiceLineItem, Payment,
    Plan, Subscription,
)
from .gateway import get_gateway


def _next_invoice_number(tenant) -> str:
    count = Invoice.all_objects.filter(tenant=tenant).count() + 1
    slug = (tenant.slug or 'x')[:6].upper()
    return f'INV-{slug}-{count:05d}'


def start_trial_for_new_tenant(tenant: Tenant) -> Subscription:
    """Create a default Subscription (14-day trial on the cheapest active plan) + branding defaults."""
    plan = Plan.objects.filter(is_active=True).order_by('sort_order', 'price_monthly').first()
    if plan is None:
        plan, _ = Plan.objects.get_or_create(
            slug='starter',
            defaults={
                'name': 'Starter',
                'description': 'Starter plan — default for new tenants.',
                'price_monthly': Decimal('29.00'),
                'price_yearly': Decimal('290.00'),
                'trial_days': 14,
                'max_users': 10,
                'max_production_orders': 500,
                'max_storage_mb': 1024,
                'features': ['Dashboard', 'User management', 'Tenant onboarding'],
                'is_active': True,
                'sort_order': 0,
            },
        )

    now = timezone.now()
    sub, _created = Subscription.objects.get_or_create(
        tenant=tenant,
        defaults={
            'plan': plan,
            'status': 'trial',
            'interval': Plan.INTERVAL_MONTHLY,
            'trial_ends_at': now + timedelta(days=plan.trial_days),
            'current_period_start': now,
            'current_period_end': now + timedelta(days=30),
        },
    )

    BrandingSettings.objects.get_or_create(
        tenant=tenant,
        defaults={'email_from_name': tenant.name, 'email_from_address': tenant.email or ''},
    )

    defaults = [
        ('welcome', 'Welcome to {{tenant_name}}',
         '<p>Hi {{user_name}},</p><p>Welcome aboard.</p>'),
        ('invite', 'You have been invited to join {{tenant_name}}',
         '<p>Click the link to accept: {{accept_url}}</p>'),
        ('password_reset', 'Reset your password',
         '<p>Reset link: {{reset_url}}</p>'),
        ('invoice_issued', 'Invoice {{invoice_number}} issued',
         '<p>Your invoice {{invoice_number}} for {{amount}} is ready.</p>'),
        ('payment_received', 'Payment received',
         '<p>We received your payment of {{amount}}.</p>'),
    ]
    for code, subject, body in defaults:
        EmailTemplate.all_objects.get_or_create(
            tenant=tenant, code=code,
            defaults={'subject': subject, 'html_body': body, 'text_body': body},
        )
    return sub


@transaction.atomic
def issue_invoice_for_subscription(sub: Subscription, *, tax_rate: Decimal = Decimal('0')) -> Invoice:
    subtotal = sub.price
    tax = (subtotal * tax_rate).quantize(Decimal('0.01'))
    total = subtotal + tax
    today = timezone.now().date()
    invoice = Invoice.objects.create(
        tenant=sub.tenant,
        subscription=sub,
        number=_next_invoice_number(sub.tenant),
        status='open',
        issue_date=today,
        due_date=today + timedelta(days=14),
        period_start=sub.current_period_start.date(),
        period_end=sub.current_period_end.date(),
        currency=sub.plan.currency,
        subtotal=subtotal,
        tax=tax,
        total=total,
    )
    InvoiceLineItem.objects.create(
        invoice=invoice,
        description=f'{sub.plan.name} ({sub.interval})',
        quantity=Decimal('1.00'),
        unit_price=subtotal,
    )
    return invoice


@transaction.atomic
def mark_invoice_paid(invoice: Invoice, *, method: str = 'card') -> Payment:
    gw = get_gateway()
    result = gw.charge(
        amount=invoice.total,
        currency=invoice.currency,
        description=f'Invoice {invoice.number}',
        metadata={'invoice_id': invoice.pk, 'tenant_id': invoice.tenant_id},
    )
    payment = Payment.objects.create(
        tenant=invoice.tenant,
        invoice=invoice,
        gateway=gw.name,
        gateway_ref=result.gateway_ref,
        amount=invoice.total,
        currency=invoice.currency,
        method=method,
        status='succeeded' if result.ok else 'failed',
        paid_at=timezone.now() if result.ok else None,
    )
    if result.ok:
        invoice.status = 'paid'
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=['status', 'paid_at'])
    return payment
