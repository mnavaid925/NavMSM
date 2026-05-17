"""Cron sweeper for process mining.

For every active ProcessDefinition in the tenant, regenerates a
BottleneckAnalysis + CycleTimeReport covering the last 30 days.

Idempotent on (tenant, definition, period_start, period_end) for the
cycle-time report; bottleneck analyses are appended.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import Tenant
from apps.wfa.models import (
    BottleneckAnalysis, CycleTimeReport, ProcessDefinition, ProcessInstance,
)
from apps.wfa.services.process_mining import (
    classify_severity, cycle_time_stats, detect_bottleneck,
)


class Command(BaseCommand):
    help = 'Refresh BottleneckAnalysis + CycleTimeReport rows for active processes.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help='Slug of a single tenant')
        parser.add_argument('--days', type=int, default=30, help='Window length (default 30)')

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if options.get('tenant'):
            tenants = tenants.filter(slug=options['tenant'])
        end = timezone.localdate()
        start = end - timedelta(days=int(options.get('days') or 30))
        total = 0
        for tenant in tenants:
            for definition in ProcessDefinition.all_objects.filter(tenant=tenant, status='active'):
                with transaction.atomic():
                    node, avg, count = detect_bottleneck(
                        definition, period_start=start, period_end=end,
                    )
                    BottleneckAnalysis.all_objects.create(
                        tenant=tenant, definition=definition,
                        period_start=start, period_end=end,
                        bottleneck_node=node,
                        avg_wait_seconds=avg,
                        instance_count=count,
                        severity=classify_severity(avg),
                    )
                    instances = ProcessInstance.all_objects.filter(
                        tenant=tenant, definition=definition, status='completed',
                        completed_at__date__gte=start, completed_at__date__lte=end,
                    )
                    n, avg_c, p95, mn, mx = cycle_time_stats(instances)
                    CycleTimeReport.all_objects.update_or_create(
                        tenant=tenant, definition=definition,
                        period_start=start, period_end=end,
                        defaults={
                            'instance_count': n,
                            'avg_cycle_seconds': avg_c,
                            'p95_cycle_seconds': p95,
                            'min_cycle_seconds': mn,
                            'max_cycle_seconds': mx,
                        },
                    )
                    total += 1
                    self.stdout.write(f'mined {definition.code} ({tenant.slug})')
        self.stdout.write(self.style.SUCCESS(f'Done. {total} definition(s) processed.'))
