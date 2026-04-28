"""Audit-log signal wiring for MES models.

Status transitions on MESWorkOrder, MESWorkOrderOperation, AndonAlert,
WorkInstruction, and WorkInstructionVersion all write to
``apps.tenants.TenantAuditLog``. Mirrors the PPS / MRP pattern.

Also handles two non-audit side-effects:
    - WorkInstructionAcknowledgement.pre_save snapshots the version string.
    - We deliberately do NOT auto-bump operation totals from
      ProductionReport.post_save - that work happens transactionally in
      ``services/reporting.py:record_production`` to keep the rollup
      explicit and bulk-create / fixture-load safe.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.core.models import get_current_tenant

from .models import (
    AndonAlert, MESWorkOrder, MESWorkOrderOperation, WorkInstruction,
    WorkInstructionAcknowledgement, WorkInstructionVersion,
)


def _tenant_audit(action, instance, tenant=None, meta=None):
    from apps.tenants.models import TenantAuditLog
    tenant = tenant or getattr(instance, 'tenant', None) or get_current_tenant()
    if tenant is None:
        return
    TenantAuditLog.objects.create(
        tenant=tenant,
        action=action,
        target_type=instance.__class__.__name__,
        target_id=str(getattr(instance, 'pk', '')),
        meta=meta or {},
    )


def _stash_status(instance, sender):
    if instance.pk:
        try:
            instance._old_status = sender.all_objects.get(pk=instance.pk).status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


# ---- MESWorkOrder ----

@receiver(pre_save, sender=MESWorkOrder)
def _stash_wo_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=MESWorkOrder)
def log_wo_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'mes_work_order.created', instance, instance.tenant,
            meta={'wo_number': instance.wo_number, 'status': instance.status},
        )
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status:
        _tenant_audit(
            f'mes_work_order.{instance.status}', instance, instance.tenant,
            meta={'wo_number': instance.wo_number, 'from': old, 'to': instance.status},
        )


# ---- MESWorkOrderOperation (status transitions only - high-frequency model) ----

@receiver(pre_save, sender=MESWorkOrderOperation)
def _stash_op_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=MESWorkOrderOperation)
def log_op_save(sender, instance, created, **kwargs):
    if created:
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status \
            and instance.status in ('running', 'paused', 'completed', 'skipped'):
        _tenant_audit(
            f'mes_op.{instance.status}', instance, instance.tenant,
            meta={
                'wo': instance.work_order.wo_number if instance.work_order_id else '',
                'sequence': instance.sequence,
                'from': old, 'to': instance.status,
            },
        )


# ---- AndonAlert ----

@receiver(pre_save, sender=AndonAlert)
def _stash_andon_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=AndonAlert)
def log_andon_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'andon.created', instance, instance.tenant,
            meta={
                'alert_number': instance.alert_number,
                'severity': instance.severity,
                'alert_type': instance.alert_type,
            },
        )
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status:
        _tenant_audit(
            f'andon.{instance.status}', instance, instance.tenant,
            meta={
                'alert_number': instance.alert_number,
                'from': old, 'to': instance.status,
            },
        )


# ---- WorkInstruction status transitions ----

@receiver(pre_save, sender=WorkInstruction)
def _stash_wi_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=WorkInstruction)
def log_wi_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'work_instruction.created', instance, instance.tenant,
            meta={
                'instruction_number': instance.instruction_number,
                'status': instance.status,
            },
        )
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status:
        _tenant_audit(
            f'work_instruction.{instance.status}', instance, instance.tenant,
            meta={
                'instruction_number': instance.instruction_number,
                'from': old, 'to': instance.status,
            },
        )


@receiver(pre_save, sender=WorkInstructionVersion)
def _stash_wiv_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=WorkInstructionVersion)
def log_wiv_save(sender, instance, created, **kwargs):
    if created:
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status \
            and instance.status in ('released', 'obsolete'):
        _tenant_audit(
            f'work_instruction_version.{instance.status}', instance, instance.tenant,
            meta={
                'instruction_number': instance.instruction.instruction_number,
                'version': instance.version,
                'from': old, 'to': instance.status,
            },
        )


# ---- Acknowledgement: snapshot the version string at save time ----

@receiver(pre_save, sender=WorkInstructionAcknowledgement)
def _snapshot_ack_version(sender, instance, **kwargs):
    if not instance.instruction_version and instance.instruction_id:
        cv = getattr(instance.instruction, 'current_version', None)
        if cv is not None:
            instance.instruction_version = cv.version
