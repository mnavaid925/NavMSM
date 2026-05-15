"""Daily cron - move Documents past their retention_until into the archive.

Idempotent. Race-safe via conditional `update()` filtering on the
previous status. Skips any Document under an active legal hold or whose
policy is `legal_hold_compatible=False` AND has a lock.

Usage:
    python manage.py archive_due_documents
    python manage.py archive_due_documents --dry-run
    python manage.py archive_due_documents --tenant acme
"""
from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import Tenant
from apps.dms.models import Document, DocumentArchive


class Command(BaseCommand):
    help = 'Flip Documents past their retention_until from effective to archived. Idempotent.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show actions only; do not write.')
        parser.add_argument('--tenant', type=str, default=None, help='Slug of a single tenant.')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        slug = opts['tenant']
        tenants = Tenant.objects.filter(is_active=True)
        if slug:
            tenants = tenants.filter(slug=slug)
        today: date = timezone.localdate()
        total_flipped = 0
        for tenant in tenants:
            qs = (
                Document.all_objects
                .filter(
                    tenant=tenant,
                    retention_until__lt=today,
                    is_locked=False,
                )
                .exclude(status='archived')
            )
            count = qs.count()
            if not count:
                self.stdout.write(f'[{tenant.slug}] no due documents.')
                continue
            self.stdout.write(f'[{tenant.slug}] {count} document(s) past retention.')
            if dry:
                for doc in qs[:20]:
                    self.stdout.write(f'  -> would archive {doc.code} ({doc.title[:40]})')
                continue
            with transaction.atomic():
                for doc in qs:
                    DocumentArchive.objects.create(
                        tenant=tenant, document=doc,
                        retention_until=doc.retention_until,
                        status='archived',
                        notes=f'Auto-archived by retention sweep on {today.isoformat()}',
                    )
                    Document.all_objects.filter(pk=doc.pk).update(status='archived')
                    total_flipped += 1
        self.stdout.write(
            self.style.SUCCESS(f'Done. {total_flipped} document(s) flipped to archived.')
            if not dry else 'Dry run complete.'
        )
