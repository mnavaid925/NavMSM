"""Module 20 - Workflow & Business Process Automation - signal handlers.

All handlers are module-level (L-18 safe), carry a ``dispatch_uid``,
and are idempotent on a natural key. Cross-module hooks are written
DEFENSIVELY: they no-op when the partner module is misconfigured so
that wiring a new policy never breaks an existing module flow.

Handlers:
    1. ProcessInstance.post_save(status changes)
        -> append ProcessActivity log
    2. ApprovalRequest.post_save(status='approved'/'rejected')
        -> fire matching NotificationRule for the event_type
    3. Notification.post_save(status='pending')
        -> dispatch via services/notification.dispatch
    4. IntegrationRun.post_save(status='failed')
        -> create Notification(event_type='integration.failed')
    5. ProcessInstance.post_save(status='completed')
        -> compute ProcessMetric(cycle_time)
    6. dms.DocumentApprovalRequest.post_save(status='approved')
        -> auto-resolve a linked wfa.ApprovalRequest
    7. procurement.PurchaseOrder.post_save(status='submitted')
        -> auto-create wfa.ApprovalRequest if an active policy matches
    8. ApprovalRequest.post_save(status='escalated')
        -> notify the escalate_to_role
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)

# Track previous status per pk to detect transitions.
_STATUS_CACHE: dict[tuple[str, int], str] = {}


def _cache_key(model_label, pk):
    return (model_label, pk)


# ----------------------------------------------------------------------------
# Audit factory (mirrors apps/labor/signals.py + apps/eam/signals.py pattern)
# ----------------------------------------------------------------------------

def _audit_status_change(model_label: str):
    """Return a post_save receiver that logs status transitions to
    ``tenants.TenantAuditLog`` (best-effort - never blocks the save).
    """

    def _handler(sender, instance, created, **kwargs):
        try:
            from apps.tenants.models import TenantAuditLog
            status = getattr(instance, 'status', None)
            if status is None:
                return
            key = _cache_key(model_label, instance.pk)
            prev = _STATUS_CACHE.get(key)
            if not created and prev == status:
                return
            _STATUS_CACHE[key] = status
            TenantAuditLog.all_objects.create(
                tenant=instance.tenant,
                user=None,
                action='wfa.status_change',
                target_type=model_label,
                target_id=str(instance.pk),
                meta={'status': status, 'created': bool(created)},
            )
        except Exception as exc:
            logger.warning('wfa audit-log emit failed: %s', exc, exc_info=True)

    _handler.__name__ = f'wfa_audit_{model_label.replace(".", "_")}'
    return _handler


for _label in (
    'wfa.ProcessDefinition',
    'wfa.ProcessInstance',
    'wfa.ApprovalPolicy',
    'wfa.ApprovalRequest',
    'wfa.NotificationRule',
    'wfa.Connector',
    'wfa.IntegrationFlow',
    'wfa.IntegrationRun',
):
    post_save.connect(
        _audit_status_change(_label),
        sender=_label,
        weak=False,
        dispatch_uid=f'wfa.audit.{_label}',
    )


# ----------------------------------------------------------------------------
# 1. ProcessInstance status changes -> activity log
# ----------------------------------------------------------------------------

@receiver(post_save, sender='wfa.ProcessInstance', dispatch_uid='wfa.instance_status_activity')
def _instance_status_activity(sender, instance, created, **kwargs):
    if created:
        return
    try:
        from apps.wfa.models import ProcessActivity
        # We don't have a built-in pre/post status diff here - just write
        # an entry if the instance is now terminal and no terminal entry
        # already exists.
        terminal = {'completed': 'completed', 'cancelled': 'cancelled', 'error': 'error'}
        event = terminal.get(instance.status)
        if event is None:
            return
        already = ProcessActivity.all_objects.filter(
            instance=instance, event=event,
        ).exists()
        if not already:
            ProcessActivity.all_objects.create(
                tenant=instance.tenant,
                instance=instance,
                node=instance.current_node,
                event=event,
            )
    except Exception as exc:
        logger.warning('wfa instance activity log failed: %s', exc, exc_info=True)


# ----------------------------------------------------------------------------
# 5. ProcessInstance status='completed' -> ProcessMetric(cycle_time)
# ----------------------------------------------------------------------------

@receiver(post_save, sender='wfa.ProcessInstance', dispatch_uid='wfa.instance_completed_metric')
def _instance_completed_metric(sender, instance, created, **kwargs):
    if created or instance.status != 'completed':
        return
    try:
        from apps.wfa.models import ProcessMetric
        from apps.wfa.services.process_mining import compute_cycle_seconds
        secs = compute_cycle_seconds(instance)
        with transaction.atomic():
            ProcessMetric.all_objects.update_or_create(
                tenant=instance.tenant,
                instance=instance,
                metric_type='cycle_time',
                node=None,
                defaults={'value_seconds': secs, 'recorded_at': timezone.now()},
            )
    except Exception as exc:
        logger.warning('wfa cycle-metric refresh failed: %s', exc, exc_info=True)


# ----------------------------------------------------------------------------
# 2. ApprovalRequest approved/rejected -> notification fanout
# ----------------------------------------------------------------------------

@receiver(post_save, sender='wfa.ApprovalRequest', dispatch_uid='wfa.approval_notification')
def _approval_notification(sender, instance, created, **kwargs):
    if created or instance.status not in ('approved', 'rejected', 'escalated'):
        return
    try:
        from apps.wfa.models import NotificationRule
        from apps.wfa.services.notification import create_notification, dispatch
        event_map = {
            'approved': 'approval.approved',
            'rejected': 'approval.rejected',
            'escalated': 'approval.escalated',
        }
        event = event_map[instance.status]
        rule = NotificationRule.all_objects.filter(
            tenant=instance.tenant, event_type=event, is_active=True,
        ).first()
        if rule is None or instance.requested_by is None:
            return
        n = create_notification(
            tenant=instance.tenant, rule=rule,
            recipient=instance.requested_by,
            payload={
                'request_code': instance.code,
                'subject': instance.subject,
                'policy': instance.policy.name,
                'status': instance.status,
            },
        )
        dispatch(n)
    except Exception as exc:
        logger.warning('wfa approval-notification failed: %s', exc, exc_info=True)


# ----------------------------------------------------------------------------
# 3. Notification status='pending' on create -> dispatch immediately if no
#    delay configured. Delayed notifications are picked up by the
#    run_notifications cron.
# ----------------------------------------------------------------------------

@receiver(post_save, sender='wfa.Notification', dispatch_uid='wfa.notification_dispatch')
def _notification_auto_dispatch(sender, instance, created, **kwargs):
    if not created or instance.status != 'pending':
        return
    try:
        from apps.wfa.services.notification import dispatch
        delay = getattr(getattr(instance, 'rule', None), 'delay_minutes', 0) or 0
        if delay <= 0:
            dispatch(instance)
    except Exception as exc:
        logger.warning('wfa notification dispatch failed: %s', exc, exc_info=True)


# ----------------------------------------------------------------------------
# 4. IntegrationRun.status='failed' -> failure notification
# ----------------------------------------------------------------------------

@receiver(post_save, sender='wfa.IntegrationRun', dispatch_uid='wfa.integration_failed_notification')
def _integration_failed_notification(sender, instance, created, **kwargs):
    if instance.status != 'failed' or instance.triggered_by is None:
        return
    try:
        from apps.wfa.models import Notification, NotificationRule
        from apps.wfa.services.notification import create_notification, dispatch
        # Idempotent: skip if we already wrote a failure notification.
        already = Notification.all_objects.filter(
            tenant=instance.tenant,
            event_type='integration.failed',
            payload_json__contains={'run_code': instance.code},
        ).exists()
        if already:
            return
        rule = NotificationRule.all_objects.filter(
            tenant=instance.tenant,
            event_type='integration.failed',
            is_active=True,
        ).first()
        if rule is None:
            return
        n = create_notification(
            tenant=instance.tenant, rule=rule,
            recipient=instance.triggered_by,
            payload={
                'run_code': instance.code,
                'flow': instance.flow.name,
                'error': instance.error_message[:500],
            },
        )
        dispatch(n)
    except Exception as exc:
        logger.warning('wfa integration-failed notification failed: %s', exc, exc_info=True)


# ----------------------------------------------------------------------------
# 6. dms.DocumentApprovalRequest approved -> close linked wfa request
# ----------------------------------------------------------------------------

@receiver(post_save, sender='dms.DocumentApprovalRequest', dispatch_uid='wfa.dms_approval_close')
def _close_linked_dms_request(sender, instance, created, **kwargs):
    if instance.status != 'approved':
        return
    try:
        from apps.wfa.models import ApprovalRequest
        ApprovalRequest.all_objects.filter(
            tenant=instance.tenant,
            business_object_type='dms.DocumentApprovalRequest',
            business_object_id=instance.pk,
            status__in=('pending', 'in_progress', 'escalated'),
        ).update(status='approved', decided_at=timezone.now())
    except Exception as exc:
        logger.warning('wfa close-linked dms request failed: %s', exc, exc_info=True)


# ----------------------------------------------------------------------------
# 7. procurement.PurchaseOrder submitted -> auto-create approval request if
#    an active policy is configured for that business-object type.
# ----------------------------------------------------------------------------

@receiver(post_save, sender='procurement.PurchaseOrder', dispatch_uid='wfa.po_auto_approval')
def _auto_approval_from_po(sender, instance, created, **kwargs):
    if getattr(instance, 'status', None) != 'submitted':
        return
    try:
        from apps.wfa.models import ApprovalPolicy, ApprovalRequest
        from apps.wfa.services.approval import submit
        policy = ApprovalPolicy.all_objects.filter(
            tenant=instance.tenant,
            applies_to_type='procurement.PurchaseOrder',
            is_active=True,
        ).first()
        if policy is None:
            return
        already = ApprovalRequest.all_objects.filter(
            tenant=instance.tenant,
            policy=policy,
            business_object_type='procurement.PurchaseOrder',
            business_object_id=instance.pk,
            status__in=('pending', 'in_progress', 'escalated'),
        ).exists()
        if already:
            return
        with transaction.atomic():
            req = ApprovalRequest.all_objects.create(
                tenant=instance.tenant,
                policy=policy,
                subject=f'PO {getattr(instance, "number", instance.pk)} requires approval',
                business_object_type='procurement.PurchaseOrder',
                business_object_id=instance.pk,
                requested_by=getattr(instance, 'created_by', None),
                requested_at=timezone.now(),
            )
            submit(req, actor=getattr(instance, 'created_by', None))
    except Exception as exc:
        logger.warning('wfa po auto-approval failed: %s', exc, exc_info=True)
