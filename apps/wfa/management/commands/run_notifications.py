"""Cron sweeper for pending notifications.

Picks up `wfa.Notification(status='pending')` rows whose `triggered_at`
plus the rule's `delay_minutes` is in the past, then dispatches them
through `services/notification.dispatch`.

Supports `--dry-run` to report what would be sent, and `--tenant <slug>`
to scope to a single tenant. Idempotent within the second.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import Tenant
from apps.wfa.models import Notification
from apps.wfa.services.notification import dispatch


class Command(BaseCommand):
    help = 'Dispatch pending wfa.Notification rows that are due.'

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
            pending = Notification.all_objects.filter(
                tenant=tenant, status='pending',
            ).select_related('rule')
            for n in pending:
                delay = getattr(getattr(n, 'rule', None), 'delay_minutes', 0) or 0
                due_at = n.triggered_at + timedelta(minutes=delay)
                if due_at > now:
                    continue
                if options.get('dry_run'):
                    self.stdout.write(f'[dry] would dispatch {n.code} ({tenant.slug})')
                    total += 1
                    continue
                dispatch(n)
                total += 1
                self.stdout.write(f'dispatched {n.code} ({tenant.slug})')
        self.stdout.write(self.style.SUCCESS(f'Done. {total} notification(s) processed.'))
