"""Daily job: flip active WarrantyRegistration rows to `expired` past end_date.

A `status` enum with a time-driven terminal state (`expired`) rots
silently unless something transitions it (L-21). This command does the
flip with a race-safe conditional `update()`, is idempotent (the filter
excludes already-flipped rows), and supports `--dry-run` + `--tenant`.

Schedule daily via cron (Linux) / Task Scheduler (Windows).
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import Tenant
from apps.rma.models import WarrantyRegistration


class Command(BaseCommand):
    help = 'Flip active warranty registrations to expired once end_date has passed.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', type=str, default=None,
                            help='Slug of a single tenant to process (default: all).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without writing.')

    def handle(self, *args, **opts):
        slug = opts.get('tenant')
        tenants = (
            Tenant.objects.filter(slug=slug)
            if slug else Tenant.objects.filter(is_active=True)
        )
        if not tenants.exists():
            self.stderr.write(self.style.WARNING('No matching tenants found.'))
            return

        today = timezone.now().date()
        grand_total = 0
        for tenant in tenants:
            qs = WarrantyRegistration.all_objects.filter(
                tenant=tenant, status='active',
                end_date__isnull=False, end_date__lt=today,
            )
            count = qs.count()
            grand_total += count
            if opts['dry_run']:
                self.stdout.write(
                    f'  [{tenant.slug}] would expire {count} registration(s).',
                )
            else:
                qs.update(status='expired')
                self.stdout.write(self.style.SUCCESS(
                    f'  [{tenant.slug}] expired {count} registration(s).',
                ))

        verb = 'would expire' if opts['dry_run'] else 'expired'
        self.stdout.write(self.style.SUCCESS(
            f'\nDone. {verb} {grand_total} warranty registration(s) total.',
        ))
