"""Operator time-log helpers.

``record_event`` appends one OperatorTimeLog row, recomputes the parent
operation's actual_minutes from the accumulated start/pause/resume/stop
sequence, and flips the operation's status according to the action.

``compute_actual_minutes`` is the pure helper that walks the time-log
sequence and sums elapsed minutes. Lifted out so it can be unit-tested
without a database fixture.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone


_RUNNING_ACTIONS = ('start_job', 'resume_job')
_PAUSED_ACTIONS = ('pause_job',)
_STOP_ACTIONS = ('stop_job',)


def compute_actual_minutes(time_logs, *, now: datetime | None = None) -> Decimal:
    """Walk start/pause/resume/stop pairs in chronological order; sum minutes.

    A trailing ``start_job`` or ``resume_job`` with no following pause/stop is
    clamped to ``now`` (defaults to ``timezone.now()``) so a long-running job
    accrues elapsed time even before the operator pushes Pause/Stop.
    """
    if now is None:
        now = timezone.now()
    sorted_logs = sorted(time_logs, key=lambda r: r.recorded_at)
    total = Decimal('0')
    open_start = None
    for row in sorted_logs:
        if row.action in _RUNNING_ACTIONS:
            if open_start is None:
                open_start = row.recorded_at
        elif row.action in _PAUSED_ACTIONS or row.action in _STOP_ACTIONS:
            if open_start is not None:
                delta = (row.recorded_at - open_start).total_seconds() / 60.0
                if delta > 0:
                    total += Decimal(str(delta))
                open_start = None
    if open_start is not None:
        delta = (now - open_start).total_seconds() / 60.0
        if delta > 0:
            total += Decimal(str(delta))
    return total.quantize(Decimal('0.01'))


def record_event(
    operator,
    action: str,
    *,
    work_order_operation=None,
    notes: str = '',
    now: datetime | None = None,
):
    """Append a time-log row + sync parent operation status / actual_minutes.

    Returns the created OperatorTimeLog instance.
    """
    from apps.mes.models import MESWorkOrder, MESWorkOrderOperation, OperatorTimeLog

    when = now or timezone.now()
    with transaction.atomic():
        log = OperatorTimeLog.all_objects.create(
            tenant=operator.tenant,
            operator=operator,
            work_order_operation=work_order_operation,
            action=action,
            recorded_at=when,
            notes=notes,
        )

        if work_order_operation is None:
            return log

        op = MESWorkOrderOperation.all_objects.select_related('work_order').get(
            pk=work_order_operation.pk,
        )

        if action == 'start_job':
            op.status = 'running'
            if op.started_at is None:
                op.started_at = when
            op.current_operator = operator.user
        elif action == 'pause_job':
            op.status = 'paused'
        elif action == 'resume_job':
            op.status = 'running'
            op.current_operator = operator.user
        elif action == 'stop_job':
            op.status = 'completed'
            op.completed_at = when
            op.current_operator = None

        # Recompute actual_minutes from the full log set for safety.
        logs = list(OperatorTimeLog.all_objects.filter(work_order_operation=op))
        op.actual_minutes = compute_actual_minutes(logs, now=when)
        op.save()

        # Auto-flip the parent work order to in_progress on first start.
        if action == 'start_job' and op.work_order.status == 'dispatched':
            wo = op.work_order
            wo.status = 'in_progress'
            wo.save()
        elif action == 'stop_job':
            wo = op.work_order
            remaining_open = MESWorkOrderOperation.all_objects.filter(
                work_order=wo,
            ).exclude(status__in=('completed', 'skipped')).exists()
            if not remaining_open and wo.status == 'in_progress':
                wo.status = 'completed'
                wo.completed_at = when
                wo.completed_by = operator.user
                wo.save()
        return log
