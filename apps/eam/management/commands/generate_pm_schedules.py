"""Idempotent next-due PM schedule generator.

Usage:
    python manage.py generate_pm_schedules
    python manage.py generate_pm_schedules --tenant <slug>
    python manage.py generate_pm_schedules --horizon-days 60

For each active MaintenancePlan, compute the next batch of upcoming schedule
dates via the pure ``generate_upcoming_pm`` service and create PMSchedule rows
that don't already exist for the (plan, scheduled_date) tuple.

Per Lesson L-09, all stdout is plain ASCII.
"""
from datetime import date

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction

from apps.core.models import Tenant
from apps.eam.models import MaintenancePlan, PMSchedule
from apps.eam.services.pm_scheduler import generate_upcoming_pm


class Command(BaseCommand):
    help = 'Generate upcoming PMSchedule rows for every active MaintenancePlan.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help='Limit to a single tenant slug.')
        parser.add_argument('--horizon-days', type=int, default=90)
        parser.add_argument('--max-per-plan', type=int, default=4)

    def handle(self, *args, **options):
        slug = options.get('tenant')
        horizon = options.get('horizon_days')
        max_per = options.get('max_per_plan')

        tenants_qs = Tenant.objects.filter(is_active=True)
        if slug:
            tenants_qs = tenants_qs.filter(slug=slug)
        tenants = list(tenants_qs)
        if not tenants:
            self.stdout.write(self.style.WARNING('No active tenants matched.'))
            return

        # Mark overdue rows first.
        today = date.today()
        overdue = PMSchedule.all_objects.filter(
            status='scheduled', scheduled_date__lt=today,
        ).update(status='overdue')
        if overdue:
            self.stdout.write(f'Flagged {overdue} schedule(s) as overdue.')

        total_created = 0
        for tenant in tenants:
            plans = MaintenancePlan.all_objects.filter(
                tenant=tenant, is_active=True,
            )
            self.stdout.write(self.style.HTTP_INFO(
                f'-> Tenant: {tenant.name} ({plans.count()} active plans)'
            ))
            tenant_count = 0
            for plan in plans:
                upcoming = generate_upcoming_pm(
                    plan, horizon_days=horizon, max_count=max_per,
                )
                for sched_date, sched_meter in upcoming:
                    if sched_date is None:
                        continue
                    if PMSchedule.all_objects.filter(
                        tenant=tenant, plan=plan, scheduled_date=sched_date,
                    ).exists():
                        continue
                    for _ in range(5):
                        try:
                            with transaction.atomic():
                                PMSchedule.all_objects.create(
                                    tenant=tenant, plan=plan,
                                    scheduled_date=sched_date,
                                    scheduled_meter=sched_meter,
                                )
                            tenant_count += 1
                            break
                        except IntegrityError:
                            continue
            self.stdout.write(f'  generated {tenant_count} new schedule(s)')
            total_created += tenant_count

        self.stdout.write(self.style.SUCCESS(
            f'Done. {total_created} new schedule(s) generated.'
        ))
