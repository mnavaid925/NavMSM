"""Daily cron - flag (but do not auto-cancel) overdue DocumentAssignments.

We report counts and the affected codes; we do NOT mutate state because
an overdue assignment is still a valid request to ack. The dashboard
shows overdue rows with a red row tint via `DocumentAssignment.is_overdue()`.

Usage:
    python manage.py expire_assignments
    python manage.py expire_assignments --dry-run
    python manage.py expire_assignments --tenant acme
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import Tenant
from apps.dms.models import DocumentAssignment


class Command(BaseCommand):
    help = 'Report DocumentAssignments past due_date with no full acknowledgment. Read-only by default.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report only (default behaviour).')
        parser.add_argument('--tenant', type=str, default=None, help='Slug of a single tenant.')

    def handle(self, *args, **opts):
        slug = opts['tenant']
        tenants = Tenant.objects.filter(is_active=True)
        if slug:
            tenants = tenants.filter(slug=slug)
        today = timezone.localdate()
        total = 0
        for tenant in tenants:
            overdue = DocumentAssignment.objects.filter(
                tenant=tenant, status='active',
                due_date__isnull=False, due_date__lt=today,
            )
            count = overdue.count()
            total += count
            if count == 0:
                self.stdout.write(f'[{tenant.slug}] no overdue assignments.')
                continue
            self.stdout.write(f'[{tenant.slug}] {count} overdue assignment(s):')
            for a in overdue[:20]:
                self.stdout.write(f'  - {a.code} due {a.due_date} ({a.document.code})')
        self.stdout.write(self.style.SUCCESS(f'Done. {total} assignment(s) overdue across all tenants.'))
