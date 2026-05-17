"""Module 20.2 - Approval engine helpers.

All state transitions go through these helpers so we can use a
race-safe ``UPDATE ... WHERE status=<prev>`` pattern (mirrors
``apps/dms/services/approval.py``).

Functions never write notifications directly - they emit log rows and
return a status flag; the caller decides whether to fire a
``NotificationRule`` based on the returned action.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone


def compute_due_at(request, level):
    """Return the due_at datetime for the current level."""
    if level is None or not getattr(level, 'sla_hours', None):
        return None
    base = request.requested_at or timezone.now()
    return base + timedelta(hours=int(level.sla_hours))


def current_level(request):
    """Return the ApprovalLevel matching ``request.current_level_no``."""
    return request.policy.levels.filter(level_no=request.current_level_no).first()


def submit(request, *, actor=None):
    """Mark the request as in_progress + stamp due_at from level 1 SLA."""
    from apps.wfa.models import ApprovalActionLog

    level = current_level(request)
    request.status = 'in_progress'
    request.current_level_no = level.level_no if level else 1
    if level and level.sla_hours:
        request.due_at = compute_due_at(request, level)
    request.save(update_fields=['status', 'current_level_no', 'due_at', 'updated_at'])
    ApprovalActionLog.all_objects.create(
        tenant=request.tenant,
        request=request,
        level_no=request.current_level_no,
        decision='submit',
        actor=actor,
    )
    return request


@transaction.atomic
def approve(request, *, actor=None, notes=''):
    """Approve at the current level. Advances to next level or completes."""
    from apps.wfa.models import (
        ApprovalActionLog, ApprovalLevel, ApprovalRequest,
    )

    cur_no = request.current_level_no
    levels = list(request.policy.levels.order_by('level_no'))
    next_level = next(
        (l for l in levels if l.level_no > cur_no), None,
    )
    log = ApprovalActionLog.all_objects.create(
        tenant=request.tenant,
        request=request,
        level_no=cur_no,
        decision='approve',
        actor=actor,
        notes=notes,
    )
    if next_level is None:
        # Final approval.
        ApprovalRequest.all_objects.filter(pk=request.pk).update(
            status='approved',
            decided_at=timezone.now(),
        )
        request.refresh_from_db()
    else:
        new_due = (timezone.now() + timedelta(hours=int(next_level.sla_hours))) if next_level.sla_hours else None
        ApprovalRequest.all_objects.filter(pk=request.pk).update(
            current_level_no=next_level.level_no,
            due_at=new_due,
        )
        request.refresh_from_db()
    return log


@transaction.atomic
def reject(request, *, actor=None, notes=''):
    """Terminal-reject the request at the current level."""
    from apps.wfa.models import ApprovalActionLog, ApprovalRequest

    log = ApprovalActionLog.all_objects.create(
        tenant=request.tenant,
        request=request,
        level_no=request.current_level_no,
        decision='reject',
        actor=actor,
        notes=notes,
    )
    ApprovalRequest.all_objects.filter(pk=request.pk).update(
        status='rejected',
        decided_at=timezone.now(),
    )
    request.refresh_from_db()
    return log


@transaction.atomic
def delegate(request, *, actor, delegate_user, notes=''):
    """Record a delegation action; the delegate may then approve on behalf."""
    from apps.wfa.models import ApprovalActionLog

    return ApprovalActionLog.all_objects.create(
        tenant=request.tenant,
        request=request,
        level_no=request.current_level_no,
        decision='delegate',
        actor=actor,
        delegated_to=delegate_user,
        notes=notes,
    )


@transaction.atomic
def escalate(request, *, actor=None, notes=''):
    """Flag the request as escalated. Does not advance level - the
    escalation rule may target a different role at the same level."""
    from apps.wfa.models import ApprovalActionLog, ApprovalRequest

    log = ApprovalActionLog.all_objects.create(
        tenant=request.tenant,
        request=request,
        level_no=request.current_level_no,
        decision='escalate',
        actor=actor,
        notes=notes,
    )
    ApprovalRequest.all_objects.filter(pk=request.pk, status__in=('pending', 'in_progress')).update(
        status='escalated',
    )
    request.refresh_from_db()
    return log


@transaction.atomic
def recall(request, *, actor=None, notes=''):
    """Requester recalls (cancels) their own pending request."""
    from apps.wfa.models import ApprovalActionLog, ApprovalRequest

    log = ApprovalActionLog.all_objects.create(
        tenant=request.tenant,
        request=request,
        level_no=request.current_level_no,
        decision='recall',
        actor=actor,
        notes=notes,
    )
    ApprovalRequest.all_objects.filter(pk=request.pk, status__in=('pending', 'in_progress', 'escalated')).update(
        status='cancelled',
        decided_at=timezone.now(),
    )
    request.refresh_from_db()
    return log


def active_delegate_for(*, tenant, delegator, policy=None, on_date=None):
    """Return the User the request should route to if the original
    approver has an active delegation, else None.

    Caller may pass an `on_date`; defaults to today.
    """
    from apps.wfa.models import ApprovalDelegation

    today = on_date or timezone.localdate()
    qs = ApprovalDelegation.all_objects.filter(
        tenant=tenant,
        delegator=delegator,
        is_active=True,
        starts_at__lte=today,
        ends_at__gte=today,
    )
    if policy is not None:
        # Prefer a policy-specific delegation over a global one.
        specific = qs.filter(policy=policy).first()
        if specific:
            return specific.delegate
    fallback = qs.filter(policy__isnull=True).first()
    return fallback.delegate if fallback else None
