from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.tenants.models import Plan


PLANS = [
    {
        'slug': 'starter', 'name': 'Starter', 'sort_order': 10,
        'description': 'For small teams getting off the ground.',
        'price_monthly': Decimal('29.00'), 'price_yearly': Decimal('290.00'),
        'trial_days': 14, 'max_users': 10, 'max_production_orders': 500, 'max_storage_mb': 1024,
        'features': ['Tenant onboarding', 'User management', 'Invoices', 'Email support'],
    },
    {
        'slug': 'growth', 'name': 'Growth', 'sort_order': 20, 'is_featured': True,
        'description': 'For growing factories with multi-site needs.',
        'price_monthly': Decimal('99.00'), 'price_yearly': Decimal('990.00'),
        'trial_days': 14, 'max_users': 50, 'max_production_orders': 5000, 'max_storage_mb': 10240,
        'features': ['Everything in Starter', 'Custom branding', 'Health monitoring', 'Priority email'],
    },
    {
        'slug': 'pro', 'name': 'Pro', 'sort_order': 30,
        'description': 'Advanced workflows and analytics.',
        'price_monthly': Decimal('249.00'), 'price_yearly': Decimal('2490.00'),
        'trial_days': 14, 'max_users': 200, 'max_production_orders': 50000, 'max_storage_mb': 51200,
        'features': ['Everything in Growth', 'Audit log export', 'API access', 'Dedicated success manager'],
    },
    {
        'slug': 'enterprise', 'name': 'Enterprise', 'sort_order': 40,
        'description': 'Custom SLAs, SSO, and compliance support.',
        'price_monthly': Decimal('0.00'), 'price_yearly': Decimal('0.00'),
        'trial_days': 30, 'max_users': 5000, 'max_production_orders': 1000000, 'max_storage_mb': 512000,
        'features': ['Everything in Pro', 'SSO / SAML', 'Custom SLA', 'On-prem options'],
    },
]


class Command(BaseCommand):
    help = 'Seed plan catalog. Idempotent via slug.'

    def handle(self, *args, **options):
        for data in PLANS:
            obj, created = Plan.objects.get_or_create(slug=data['slug'], defaults=data)
            if not created:
                # refresh soft fields
                for k, v in data.items():
                    if k != 'slug':
                        setattr(obj, k, v)
                obj.save()
            self.stdout.write(self.style.SUCCESS(f'{"created" if created else "updated"}: {obj.name}'))
