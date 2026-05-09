"""Sub-module 13.1 services - EHS incident lifecycle helpers.

Pure-ish writers wrapped in atomic blocks. All status transitions go via
``compliance.views._atomic_status_transition`` so the audit signal sees the
flip; these helpers just centralize the field updates.
"""
from django.db import transaction
from django.utils import timezone

from apps.compliance import models


@transaction.atomic
def record_investigation(incident, *, root_cause, by=None):
    """Persist root_cause and flip the incident to ``investigating``."""
    if not incident.is_investigatable():
        return incident
    incident.root_cause = root_cause
    incident.status = 'investigating'
    incident.save(update_fields=['root_cause', 'status', 'updated_at'])
    return incident


@transaction.atomic
def record_corrective_action(incident, *, corrective_actions, by=None):
    if not incident.is_actionable():
        return incident
    incident.corrective_actions = corrective_actions
    incident.status = 'corrective_action'
    incident.save(update_fields=['corrective_actions', 'status', 'updated_at'])
    return incident


@transaction.atomic
def close_incident(incident, *, by=None):
    if not incident.is_closeable():
        return incident
    incident.status = 'closed'
    incident.closed_at = timezone.now()
    incident.closed_by = by
    incident.save(update_fields=['status', 'closed_at', 'closed_by', 'updated_at'])
    return incident


@transaction.atomic
def cancel_incident(incident, *, reason, by=None):
    if not incident.is_cancellable():
        return incident
    incident.status = 'cancelled'
    incident.cancellation_reason = reason
    incident.save(
        update_fields=['status', 'cancellation_reason', 'updated_at'],
    )
    return incident
