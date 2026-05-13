"""Report scheduling + email distribution.

The management command ``run_report_schedules`` invokes ``sweep_due()``,
which loops every active ``ReportSchedule`` whose ``next_run_at <= now``,
renders its bound report (or dashboard summary), creates a
``ReportExport``, fans out ``ReportDelivery`` rows, sends emails via
Django ``send_mail``, and advances ``next_run_at`` based on the frequency.

Idempotency: a single ``(schedule, next_run_at)`` execution will only
fire once per scheduled timestamp - reruns within the same minute see
``last_run_at >= next_run_at - 1s`` and skip.
"""
from __future__ import annotations

from datetime import timedelta
from typing import List

from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from . import reports as reports_service


def _advance_next_run(schedule, now=None):
    """Compute the next ``next_run_at`` from frequency. Cron is naive in v1."""
    now = now or timezone.now()
    f = schedule.frequency
    if f == 'daily':
        return now + timedelta(days=1)
    if f == 'weekly':
        return now + timedelta(days=7)
    if f == 'monthly':
        return now + timedelta(days=30)
    # custom: fall back to daily for v1.
    return now + timedelta(days=1)


def due_schedules(tenant=None, now=None):
    """Return active schedules whose ``next_run_at <= now``.

    If ``tenant`` is None, sweeps every tenant (use from management command).
    """
    from apps.bi.models import ReportSchedule
    now = now or timezone.now()
    qs = ReportSchedule.all_objects.filter(
        status='active', next_run_at__lte=now,
    )
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    return qs.order_by('next_run_at')


@transaction.atomic
def run_schedule(schedule, now=None) -> List:
    """Execute one schedule. Returns the list of ``ReportDelivery`` rows created.

    Steps:
        1. Render the bound report -> CSV text + row count
        2. Create a ``ReportExport`` row with the file content
        3. Create one ``ReportDelivery`` per active recipient
        4. Send the emails (console backend in dev)
        5. Update schedule ``last_run_at`` / ``next_run_at``
    """
    from apps.bi.models import (
        ReportDelivery, ReportExport, ReportSchedule,
    )

    now = now or timezone.now()
    deliveries: List[ReportDelivery] = []

    # Skip if we already ran for this scheduled instant.
    if schedule.last_run_at and schedule.last_run_at >= schedule.next_run_at - timedelta(seconds=1):
        return deliveries

    csv_text = ''
    row_count = 0
    if schedule.report:
        try:
            run, rows, csv_text = reports_service.run_and_persist(
                schedule.report, schedule.tenant, user=schedule.created_by,
            )
            row_count = run.row_count
        except Exception as exc:  # noqa: BLE001
            schedule.last_status = f'failed: {exc}'[:200]
            schedule.last_run_at = now
            schedule.next_run_at = _advance_next_run(schedule, now=now)
            schedule.save(update_fields=['last_status', 'last_run_at', 'next_run_at'])
            return deliveries
    elif schedule.dashboard:
        # Dashboard exports render a CSV of widget snapshot values.
        from apps.bi.models import KPISnapshot
        widget_codes = [w.kpi_definition.code for w in schedule.dashboard.widgets.all()]
        snaps = (
            KPISnapshot.all_objects
            .filter(tenant=schedule.tenant, kpi_definition__code__in=widget_codes)
            .order_by('-period_end')[:50]
        )
        lines = ['kpi,period_start,period_end,value,status']
        for s in snaps:
            lines.append(
                f'{s.kpi_definition.code},{s.period_start},{s.period_end},{s.value},{s.status}'
            )
        csv_text = '\n'.join(lines)
        row_count = max(len(lines) - 1, 0)

    # Persist the export.
    export = ReportExport(
        tenant=schedule.tenant,
        report=schedule.report,
        dashboard=schedule.dashboard,
        format=schedule.format,
        row_count=row_count,
        status='ready',
        generated_at=now,
        generated_by=schedule.created_by,
    )
    if csv_text:
        filename = f'{schedule.schedule_number}_{now:%Y%m%d_%H%M%S}.csv'
        export.file = ContentFile(csv_text.encode('utf-8'), name=filename)
        export.file_size_bytes = len(csv_text.encode('utf-8'))
    export.save()

    # Fan out deliveries.
    subject = f'[NavMSM] {schedule.name} ({now:%Y-%m-%d})'
    body = (
        f'Scheduled report: {schedule.name}\n'
        f'Rows: {row_count}\n'
        f'Run at: {now:%Y-%m-%d %H:%M:%S %Z}\n\n'
        f'See attached file for results.'
    )
    for recipient in schedule.recipients.filter(is_active=True):
        delivery = ReportDelivery(
            tenant=schedule.tenant,
            schedule=schedule,
            recipient=recipient,
            export=export,
            attempted_at=now,
            status='pending',
            subject=subject,
        )
        delivery.save()
        try:
            msg = EmailMessage(
                subject=subject,
                body=body,
                from_email=None,
                to=[recipient.email],
            )
            if csv_text:
                msg.attach(filename or 'report.csv', csv_text, 'text/csv')
            msg.send(fail_silently=False)
            delivery.status = 'sent'
            delivery.delivered_at = timezone.now()
            delivery.save(update_fields=['status', 'delivered_at'])
        except Exception as exc:  # noqa: BLE001
            delivery.status = 'failed'
            delivery.error_message = str(exc)[:500]
            delivery.save(update_fields=['status', 'error_message'])
        deliveries.append(delivery)

    schedule.last_run_at = now
    schedule.last_status = f'sent {len(deliveries)} delivery(s)'[:200]
    schedule.next_run_at = _advance_next_run(schedule, now=now)
    schedule.save(update_fields=['last_run_at', 'last_status', 'next_run_at'])
    return deliveries


def sweep_due(tenant=None, now=None) -> int:
    """Iterate every due schedule and run it. Returns count of schedules run."""
    count = 0
    for schedule in due_schedules(tenant=tenant, now=now):
        run_schedule(schedule, now=now)
        count += 1
    return count
