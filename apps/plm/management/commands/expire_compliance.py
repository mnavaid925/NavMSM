"""D-CR-02: flip ProductCompliance rows from `compliant` to `expired` when their
`expiry_date < today`.

Idempotent — second run is a no-op (the `compliant` filter excludes already-flipped
rows). Designed to run daily via cron / Task Scheduler.

Writes a `ComplianceAuditLog(event='expired')` row per flip and a
`tenants.TenantAuditLog(action='compliance.status.expired')` row, both inside a
single transaction per tenant batch so a crash mid-flight doesn't leave audit
gaps.

Usage:
    python manage.py expire_compliance              # all tenants
    python manage.py expire_compliance --tenant acme  # single tenant by slug
    python manage.py expire_compliance --dry-run    # report only, no writes
"""
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import Tenant, set_current_tenant
from apps.plm.models import ComplianceAuditLog, ProductCompliance


class Command(BaseCommand):
    help = (
        'Flip ProductCompliance rows from `compliant` to `expired` when their '
        'expiry_date < today. Idempotent. Writes one ComplianceAuditLog per flip.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--tenant', type=str, default=None,
                            help='Restrict to a single tenant by slug.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without writing.')

    def handle(self, *args, **options):
        today = date.today()
        tenants_qs = Tenant.objects.filter(is_active=True)
        if options['tenant']:
            tenants_qs = tenants_qs.filter(slug=options['tenant'])

        total_flipped = 0
        for tenant in tenants_qs:
            set_current_tenant(tenant)
            stale = list(
                ProductCompliance.objects.filter(
                    tenant=tenant, status='compliant', expiry_date__lt=today,
                ).values_list('pk', 'product__sku', 'standard__code'),
            )
            if not stale:
                continue

            self.stdout.write(
                f'  {tenant.slug}: {len(stale)} compliant record(s) past expiry'
            )
            for pk, sku, std_code in stale:
                self.stdout.write(f'    - PC#{pk} {sku} :: {std_code}')

            if options['dry_run']:
                continue

            # Race-safe: re-filter on status='compliant' inside the UPDATE so
            # any concurrent manual edit that already flipped the row wins.
            with transaction.atomic():
                rowcount = ProductCompliance.objects.filter(
                    tenant=tenant, status='compliant', expiry_date__lt=today,
                ).update(status='expired')
                # Emit one immutable audit row per actually-flipped record.
                # We re-read via the post-update predicate to grab the survivors.
                flipped = ProductCompliance.objects.filter(
                    tenant=tenant, status='expired', expiry_date__lt=today,
                    pk__in=[pk for pk, *_ in stale],
                )
                for rec in flipped:
                    # Skip if an `expired` audit row already exists (idempotency
                    # guard against partial prior runs).
                    already = ComplianceAuditLog.all_objects.filter(
                        compliance=rec, event='expired',
                    ).exists()
                    if already:
                        continue
                    ComplianceAuditLog.objects.create(
                        tenant=tenant, compliance=rec, event='expired',
                        meta={'expiry_date': str(rec.expiry_date), 'reason': 'auto-expired by expire_compliance'},
                    )
                    _emit_tenant_audit(tenant, rec)
                total_flipped += rowcount

        set_current_tenant(None)
        verb = 'WOULD flip' if options['dry_run'] else 'flipped'
        self.stdout.write(self.style.SUCCESS(
            f'expire_compliance: {verb} {total_flipped} record(s).'
        ))


def _emit_tenant_audit(tenant, rec):
    """Mirror the cross-cutting tenant audit feed (parity with signals.py)."""
    from apps.tenants.models import TenantAuditLog
    TenantAuditLog.objects.create(
        tenant=tenant,
        action='compliance.status.expired',
        target_type=rec.__class__.__name__,
        target_id=str(rec.pk),
        meta={
            'product': rec.product.sku, 'standard': rec.standard.code,
            'from': 'compliant', 'to': 'expired',
            'expiry_date': str(rec.expiry_date),
        },
    )
