"""Audit-log signal wiring for MRP models.

Status transitions on MRPRun, MRPCalculation, MRPPurchaseRequisition, and
MRPException all write to apps.tenants.TenantAuditLog. Mirrors the PPS / BOM
signal pattern.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.core.models import get_current_tenant

from .models import (
    MRPCalculation, MRPException, MRPPurchaseRequisition, MRPRun,
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


# ---- MRPRun status tracking ----

@receiver(pre_save, sender=MRPRun)
def _stash_run_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=MRPRun)
def log_run_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'mrp_run.created', instance, instance.tenant,
            meta={'run_number': instance.run_number,
                  'run_type': instance.run_type, 'status': instance.status},
        )
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status:
        _tenant_audit(
            f'mrp_run.{instance.status}', instance, instance.tenant,
            meta={'run_number': instance.run_number,
                  'from': old, 'to': instance.status},
        )


# ---- MRPCalculation status tracking ----

@receiver(pre_save, sender=MRPCalculation)
def _stash_calc_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=MRPCalculation)
def log_calc_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'mrp_calculation.created', instance, instance.tenant,
            meta={'mrp_number': instance.mrp_number, 'status': instance.status},
        )
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status:
        _tenant_audit(
            f'mrp_calculation.status.{instance.status}', instance, instance.tenant,
            meta={'mrp_number': instance.mrp_number, 'from': old, 'to': instance.status},
        )


# ---- MRPPurchaseRequisition status tracking ----

@receiver(pre_save, sender=MRPPurchaseRequisition)
def _stash_pr_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=MRPPurchaseRequisition)
def log_pr_save(sender, instance, created, **kwargs):
    if created:
        # PRs are auto-generated in bulk; only log explicit user-facing approvals.
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status \
            and instance.status in ('approved', 'cancelled', 'converted'):
        _tenant_audit(
            f'mrp_pr.{instance.status}', instance, instance.tenant,
            meta={'pr_number': instance.pr_number, 'from': old, 'to': instance.status},
        )


# ---- MRPException status tracking ----

@receiver(pre_save, sender=MRPException)
def _stash_exc_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=MRPException)
def log_exc_save(sender, instance, created, **kwargs):
    if created:
        # Exceptions are bulk-created by the engine; skip noisy create logs.
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status \
            and instance.status in ('acknowledged', 'resolved', 'ignored'):
        _tenant_audit(
            f'mrp_exception.{instance.status}', instance, instance.tenant,
            meta={'exception_type': instance.exception_type,
                  'from': old, 'to': instance.status},
        )
