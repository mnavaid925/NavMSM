"""Assignment fan-out helpers - given an Assignment + its Targets,
return the set of Users expected to acknowledge.

ReadAcknowledgment rows are NOT created up-front; they are written when
each user actually clicks the Acknowledge button. This service is only
used to compute the "expected" denominator on the UI.
"""
from __future__ import annotations

from typing import Iterable

from django.contrib.auth import get_user_model


def expected_users_for(assignment) -> list:
    """Return a deduplicated list of Users targeted by an assignment.

    Iterates `assignment.targets.all()` and unions the resolved user
    sets. Tenant-scoped throughout.
    """
    User = get_user_model()
    tenant = assignment.tenant
    out: set = set()
    for tgt in assignment.targets.all():
        if tgt.user_id:
            out.add(tgt.user_id)
            continue
        if tgt.employee_id and tgt.employee and tgt.employee.user_id:
            out.add(tgt.employee.user_id)
            continue
        # Role-based fan-out: every active User in the tenant matching `role`.
        if tgt.role:
            qs = User.objects.filter(
                tenant=tenant, role=tgt.role, is_active=True,
            ).values_list('id', flat=True)
            out.update(qs)
            continue
        # Department-based: every Employee linked to a User in this department.
        if tgt.department_id:
            from apps.labor.models import Employee
            user_ids = (
                Employee.objects.filter(
                    tenant=tenant, department_id=tgt.department_id,
                ).exclude(user__isnull=True).values_list('user_id', flat=True)
            )
            out.update(user_ids)
            continue
        # Position-based: every Employee with that position who has a User link.
        if tgt.position_id:
            from apps.labor.models import Employee
            user_ids = (
                Employee.objects.filter(
                    tenant=tenant, position_id=tgt.position_id,
                ).exclude(user__isnull=True).values_list('user_id', flat=True)
            )
            out.update(user_ids)
            continue
    return list(out)


def has_acknowledged(assignment, user) -> bool:
    """Cheap helper for the dashboard "my pending acks" widget."""
    return assignment.acknowledgments.filter(acknowledger=user).exists()


def pending_users_for(assignment) -> list:
    """Expected minus already-acknowledged."""
    expected = set(expected_users_for(assignment))
    acked = set(
        assignment.acknowledgments.values_list('acknowledger_id', flat=True),
    )
    return list(expected - acked)
