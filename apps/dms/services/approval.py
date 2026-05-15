"""Approval workflow helpers for `dms.DocumentApprovalRequest`.

Each ApprovalWorkflow has ordered `ApprovalStage` rows. A request walks
the stages: when enough approve actions land at the current stage, it
advances; on reject, the whole request terminates.
"""
from __future__ import annotations

from typing import Optional


def stages_for(request) -> list:
    """Return the list of ApprovalStage rows for the request's workflow,
    ordered by stage_no.
    """
    return list(request.workflow.stages.order_by('stage_no'))


def current_stage(request):
    """Return the ApprovalStage matching `request.current_stage_no`, or None."""
    return next(
        (s for s in stages_for(request) if s.stage_no == request.current_stage_no),
        None,
    )


def stage_approval_count(request, stage_no: int) -> int:
    return request.actions.filter(stage_no=stage_no, decision='approve').count()


def is_stage_complete(request, stage_no: int) -> bool:
    """Has the request collected enough approvals at `stage_no`?"""
    stage = next(
        (s for s in stages_for(request) if s.stage_no == stage_no),
        None,
    )
    if stage is None:
        return False
    return stage_approval_count(request, stage_no) >= stage.min_approvals


def advance_stage(request) -> Optional[int]:
    """If the current stage is complete, advance to the next stage.

    Returns the new `current_stage_no`, or None if there are no more stages
    (in which case the caller should mark the request `approved`).
    """
    if not is_stage_complete(request, request.current_stage_no):
        return request.current_stage_no
    stages = stages_for(request)
    next_stages = [s for s in stages if s.stage_no > request.current_stage_no]
    if not next_stages:
        return None  # no more stages - caller marks approved
    return next_stages[0].stage_no


def can_take_action(request, user) -> bool:
    """Defensive guard - the view layer should also enforce RBAC.

    For v1 we allow any tenant-admin user to record an approval action at
    any stage. Stage.approver_role is informational metadata.
    """
    return getattr(user, 'is_tenant_admin', False) or getattr(user, 'is_superuser', False)
