"""Sweep due ReportSchedule rows and execute them.

Intended for cron / Windows Task Scheduler:

    Linux:  */5 * * * * cd /app && python manage.py run_report_schedules
    Win:    schtasks /create /tn "NavMSM-BI" /tr "python manage.py run_report_schedules" /sc minute /mo 5

Idempotent within the current period (skips schedules whose last_run_at
is within 1 second of next_run_at).
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.bi.services import scheduler as scheduler_svc


class Command(BaseCommand):
    help = 'Execute every active ReportSchedule whose next_run_at <= now.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help='Limit to a single tenant slug.')

    def handle(self, *args, **options):
        slug = options.get('tenant')
        tenant = None
        if slug:
            from apps.core.models import Tenant
            tenant = Tenant.objects.filter(slug=slug).first()
            if tenant is None:
                self.stdout.write(self.style.ERROR(f'No tenant with slug {slug!r}.'))
                return

        now = timezone.now()
        count = scheduler_svc.sweep_due(tenant=tenant, now=now)
        self.stdout.write(self.style.SUCCESS(
            f'Ran {count} schedule(s) at {now:%Y-%m-%d %H:%M:%S %Z}.'
        ))
