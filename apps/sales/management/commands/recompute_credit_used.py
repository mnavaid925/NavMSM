"""Recompute the `Customer.credit_used` denorm from authoritative ledgers.

Used to repair drift between the denorm column and the actual outstanding
balance (sum of unpaid SalesInvoice grand_totals plus sum of unfulfilled
SalesOrder grand_totals for confirmed/in-progress orders).

Idempotent. Safe to run repeatedly. Schedule daily via cron / Task
Scheduler if needed, or run on-demand when drift is suspected.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from apps.core.models import Tenant
from apps.sales.models import Customer, SalesInvoice, SalesOrder


class Command(BaseCommand):
    help = ('Idempotent recomputation of Customer.credit_used from open '
            'SalesOrder + unpaid SalesInvoice totals.')

    def add_arguments(self, parser):
        parser.add_argument('--tenant', type=str, default=None,
                            help='Slug of a single tenant to scan (default: all).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Print would-be updates without writing.')

    def handle(self, *args, **opts):
        slug = opts.get('tenant')
        tenants = (
            Tenant.objects.filter(slug=slug)
            if slug else Tenant.objects.filter(is_active=True)
        )
        if not tenants.exists():
            self.stderr.write(self.style.WARNING('No matching tenants.'))
            return

        OPEN_SO_STATES = ('confirmed', 'in_production', 'fulfilled', 'invoiced')
        UNPAID_INV_STATES = ('issued', 'overdue')
        total_changed = 0

        for tenant in tenants:
            self.stdout.write(self.style.MIGRATE_HEADING(f'\nTenant: {tenant.slug}'))
            for cust in Customer.all_objects.filter(tenant=tenant):
                open_so = SalesOrder.all_objects.filter(
                    tenant=tenant, customer=cust, status__in=OPEN_SO_STATES,
                ).aggregate(s=Sum('grand_total'))['s'] or Decimal('0')
                unpaid_inv = SalesInvoice.all_objects.filter(
                    tenant=tenant, sales_order__customer=cust,
                    status__in=UNPAID_INV_STATES,
                ).aggregate(s=Sum('grand_total'))['s'] or Decimal('0')
                expected = open_so + unpaid_inv
                if cust.credit_used != expected:
                    diff = expected - (cust.credit_used or Decimal('0'))
                    self.stdout.write(
                        f'  {cust.code} {cust.name}: '
                        f'was {cust.credit_used} -> {expected} '
                        f'(delta {diff:+})',
                    )
                    if not opts['dry_run']:
                        cust.credit_used = expected
                        cust.save(update_fields=['credit_used', 'updated_at'])
                    total_changed += 1
        verb = 'Would update' if opts['dry_run'] else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'\n{verb} {total_changed} customer(s).',
        ))
