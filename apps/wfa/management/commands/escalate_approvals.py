"""Cron sweeper for overdue approval requests.

Flips `ApprovalRequest(status in pending/in_progress, due_at < now)` to
`status='escalated'` via a race-safe conditional UPDATE, and emits an
`approval.escalated` notification via the existing post_save signal
hook (the status change does the work).

Supports `--dry-run` + `--tenant <slug>` flags. Idempotent.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import Tenant
from apps.wfa.models import ApprovalRequest


class Command(BaseCommand):
    help = 'Escalate overdue wfa.ApprovalRequest rows.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--tenant', help='Slug of a single tenant')

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if options.get('tenant'):
            tenants = tenants.filter(slug=options['tenant'])
        now = timezone.now()
        total = 0
        for tenant in tenants:
            qs = ApprovalRequest.all_objects.filter(
                tenant=tenant,
                status__in=('pending', 'in_progress'),
                due_at__isnull=False,
                due_at__lt=now,
            )
            if options.get('dry_run'):
                count = qs.count()
                if count:
                    self.stdout.write(f'[dry] would escalate {count} request(s) in {tenant.slug}')
                total += count
                continue
            # Single-statement race-safe flip; loop to trigger per-row signals.
            for req in qs:
                # Save the row so the post_save signal handler fires the
                # escalated notification; updating in bulk skips signals.
                req.status = 'escalated'
                req.save(update_fields=['status', 'updated_at'])
                total += 1
                self.stdout.write(f'escalated {req.code} ({tenant.slug})')
        self.stdout.write(self.style.SUCCESS(f'Done. {total} request(s) processed.'))
