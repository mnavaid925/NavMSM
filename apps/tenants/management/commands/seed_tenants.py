import random
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, UserProfile, UserInvite
from apps.core.models import Tenant, set_current_tenant
from apps.tenants.models import (
    BrandingSettings, EmailTemplate, Invoice, InvoiceLineItem, Payment,
    Plan, Subscription, TenantAuditLog, TenantHealthSnapshot,
)

try:
    from faker import Faker
    fake = Faker()
except ImportError:
    fake = None


TENANT_FIXTURES = [
    ('Acme Manufacturing', 'acme', 'admin@acme.example.com', 'Automotive'),
    ('Globex Industries', 'globex', 'admin@globex.example.com', 'Electronics'),
    ('Stark Production Co.', 'stark', 'admin@stark.example.com', 'Aerospace'),
]


def _mk_user(tenant, username, email, first, last, role, is_admin=False, password='Welcome@123'):
    """Idempotent upsert of a demo user. Always resets password + tenant + role
    so re-running the seeder produces a predictable login."""
    u, _created = User.objects.get_or_create(
        username=username,
        defaults={
            'email': email, 'first_name': first, 'last_name': last,
            'role': role, 'is_tenant_admin': is_admin, 'tenant': tenant,
            'is_active': True,
        },
    )
    u.email = email
    u.first_name = first
    u.last_name = last
    u.tenant = tenant
    u.role = role
    u.is_tenant_admin = is_admin
    u.is_active = True
    u.set_password(password)
    u.save()
    UserProfile.objects.get_or_create(user=u)
    return u


class Command(BaseCommand):
    help = 'Seed demo tenants, users, invites, subscriptions, invoices, branding, and health snapshots. Idempotent.'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Delete demo tenants first.')

    @transaction.atomic
    def handle(self, *args, **options):
        # Ensure plan catalog exists
        if not Plan.objects.exists():
            from .seed_plans import PLANS
            for data in PLANS:
                Plan.objects.get_or_create(slug=data['slug'], defaults=data)

        if options['flush']:
            Tenant.objects.filter(slug__in=[slug for _, slug, *_ in TENANT_FIXTURES]).delete()

        plans = list(Plan.objects.filter(is_active=True).order_by('sort_order'))

        created_admins = []
        for name, slug, email, industry in TENANT_FIXTURES:
            tenant, created = Tenant.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'email': email, 'industry': industry, 'is_active': True},
            )
            set_current_tenant(tenant)
            self.stdout.write(self.style.SUCCESS(f'tenant: {tenant}'))

            # Tenant admin
            admin = _mk_user(
                tenant, username=f'admin_{slug}', email=email,
                first=name.split()[0], last='Admin', role='tenant_admin', is_admin=True,
            )
            created_admins.append((admin.username, 'Welcome@123', tenant.name))

            # Staff users
            if User.objects.filter(tenant=tenant).count() < 5:
                staff_roles = ['production_manager', 'supervisor', 'operator', 'quality_inspector']
                for i, role in enumerate(staff_roles, start=1):
                    if fake:
                        first = fake.first_name()
                        last = fake.last_name()
                    else:
                        first, last = f'User{i}', slug.capitalize()
                    _mk_user(
                        tenant,
                        username=f'{slug}_{role}_{i}',
                        email=f'{role}{i}@{slug}.example.com',
                        first=first, last=last, role=role,
                    )

            # Pending invites
            if UserInvite.all_objects.filter(tenant=tenant).count() < 2:
                for i in range(2):
                    email_addr = fake.email() if fake else f'invite{i}@{slug}.example.com'
                    UserInvite.objects.create(
                        tenant=tenant,
                        email=email_addr,
                        role='operator',
                        invited_by=admin,
                        expires_at=timezone.now() + timedelta(days=7),
                        status='pending',
                    )

            # Subscription
            sub, sub_created = Subscription.objects.get_or_create(
                tenant=tenant,
                defaults={
                    'plan': random.choice(plans),
                    'status': random.choice(['trial', 'active', 'active']),
                    'interval': 'monthly',
                    'trial_ends_at': timezone.now() + timedelta(days=14),
                    'current_period_start': timezone.now() - timedelta(days=5),
                    'current_period_end': timezone.now() + timedelta(days=25),
                },
            )

            # Branding defaults
            BrandingSettings.objects.get_or_create(
                tenant=tenant,
                defaults={
                    'email_from_name': tenant.name,
                    'email_from_address': tenant.email,
                    'footer_text': f'{tenant.name} powered by NavMSM',
                    'support_email': tenant.email,
                },
            )

            # Email templates
            tmpls = [
                ('welcome', 'Welcome to {{tenant_name}}', '<p>Hi {{user_name}}, welcome!</p>'),
                ('invite', 'Join {{tenant_name}}', '<p>Accept: {{accept_url}}</p>'),
                ('password_reset', 'Reset password', '<p>Reset: {{reset_url}}</p>'),
                ('invoice_issued', 'Invoice {{invoice_number}}', '<p>Your invoice is ready.</p>'),
                ('payment_received', 'Payment received', '<p>We received your payment.</p>'),
            ]
            for code, subj, body in tmpls:
                EmailTemplate.all_objects.get_or_create(
                    tenant=tenant, code=code,
                    defaults={'subject': subj, 'html_body': body, 'text_body': body},
                )

            # Invoices + Payments
            if Invoice.objects.filter(tenant=tenant).count() < 3:
                today = timezone.now().date()
                for i in range(random.randint(3, 6)):
                    issue = today - timedelta(days=30 * i)
                    status = 'paid' if i > 0 else 'open'
                    subtotal = sub.price
                    tax = (subtotal * Decimal('0.00')).quantize(Decimal('0.01'))
                    total = subtotal + tax
                    inv = Invoice.objects.create(
                        tenant=tenant,
                        subscription=sub,
                        number=f'INV-{slug[:6].upper()}-{i+1:05d}',
                        status=status,
                        issue_date=issue,
                        due_date=issue + timedelta(days=14),
                        period_start=issue,
                        period_end=issue + timedelta(days=30),
                        currency=sub.plan.currency,
                        subtotal=subtotal, tax=tax, total=total,
                    )
                    InvoiceLineItem.objects.create(
                        invoice=inv,
                        description=f'{sub.plan.name} ({sub.interval})',
                        quantity=Decimal('1.00'), unit_price=subtotal,
                    )
                    if status == 'paid':
                        Payment.objects.create(
                            tenant=tenant, invoice=inv,
                            gateway='mock', gateway_ref=f'mock_seed_{tenant.slug}_{i}',
                            amount=total, currency=sub.plan.currency,
                            method='card', status='succeeded',
                            paid_at=timezone.make_aware(datetime.combine(issue + timedelta(days=2), datetime.min.time())),
                        )
                        inv.paid_at = timezone.make_aware(datetime.combine(issue + timedelta(days=2), datetime.min.time()))
                        inv.save(update_fields=['paid_at'])

            # Health snapshots — last 30 days
            if TenantHealthSnapshot.objects.filter(tenant=tenant).count() < 10:
                for d in range(30, 0, -1):
                    TenantHealthSnapshot.objects.create(
                        tenant=tenant,
                        captured_at=timezone.now() - timedelta(days=d),
                        active_users=random.randint(3, 40),
                        storage_mb=random.randint(150, 8000),
                        api_calls_24h=random.randint(200, 12000),
                        error_rate=Decimal(str(round(random.uniform(0.0, 2.5), 2))),
                        avg_response_ms=random.randint(80, 420),
                        health_score=Decimal(str(round(random.uniform(78, 99), 2))),
                    )

            # Audit entries
            if TenantAuditLog.objects.filter(tenant=tenant).count() < 5:
                for action in ['tenant.created', 'subscription.created', 'branding.created', 'invoice.issued', 'user.invited']:
                    TenantAuditLog.objects.create(
                        tenant=tenant, user=admin, action=action,
                        target_type='system', target_id='1',
                        ip_address='127.0.0.1', user_agent='seeder',
                    )

        set_current_tenant(None)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Seed complete.'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write('Tenant admin logins (all with password Welcome@123):')
        for username, pwd, tname in created_admins:
            self.stdout.write(f'  - {username} / {pwd}  ({tname})')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'NOTE: The Django superuser `admin` has tenant=None — data will NOT appear when logged in as admin. '
            'Use one of the tenant admin accounts above to see tenant-scoped data.'
        ))
