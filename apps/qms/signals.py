"""Audit-log signal wiring for QMS models.

Status transitions on IncomingInspection, ProcessInspection, FinalInspection,
NonConformanceReport, CertificateOfAnalysis, CorrectiveAction, PreventiveAction
all write to ``apps.tenants.TenantAuditLog``. Mirrors the MES / MRP / PPS
pattern.

CalibrationRecord.post_save also propagates ``last_calibrated_at`` and
``next_due_at`` back onto the parent MeasurementEquipment row via a single
``update()`` (Lesson L-15 - capture the new value in a local before the
``update()`` call so the in-memory equipment instance does not go stale).
"""
from datetime import timedelta

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.core.models import get_current_tenant

from .models import (
    CalibrationRecord, CertificateOfAnalysis, CorrectiveAction,
    FinalInspection, IncomingInspection, MeasurementEquipment,
    NonConformanceReport, PreventiveAction, ProcessInspection,
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


# ---- IncomingInspection ----

@receiver(pre_save, sender=IncomingInspection)
def _stash_iqc_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=IncomingInspection)
def log_iqc_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'qms_iqc.created', instance, instance.tenant,
            meta={'inspection_number': instance.inspection_number,
                  'status': instance.status},
        )
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status:
        _tenant_audit(
            f'qms_iqc.{instance.status}', instance, instance.tenant,
            meta={'inspection_number': instance.inspection_number,
                  'from': old, 'to': instance.status},
        )


# ---- ProcessInspection ----

@receiver(pre_save, sender=ProcessInspection)
def _stash_ipqc_result(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_result = sender.all_objects.get(pk=instance.pk).result
        except sender.DoesNotExist:
            instance._old_result = None
    else:
        instance._old_result = None


@receiver(post_save, sender=ProcessInspection)
def log_ipqc_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'qms_ipqc.created', instance, instance.tenant,
            meta={'inspection_number': instance.inspection_number,
                  'result': instance.result},
        )
        return
    old = getattr(instance, '_old_result', None)
    if old is not None and old != instance.result:
        _tenant_audit(
            f'qms_ipqc.result_{instance.result}', instance, instance.tenant,
            meta={'inspection_number': instance.inspection_number,
                  'from': old, 'to': instance.result},
        )


# ---- FinalInspection ----

@receiver(pre_save, sender=FinalInspection)
def _stash_fqc_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=FinalInspection)
def log_fqc_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'qms_fqc.created', instance, instance.tenant,
            meta={'inspection_number': instance.inspection_number,
                  'status': instance.status},
        )
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status:
        _tenant_audit(
            f'qms_fqc.{instance.status}', instance, instance.tenant,
            meta={'inspection_number': instance.inspection_number,
                  'from': old, 'to': instance.status},
        )


# ---- CertificateOfAnalysis ----

@receiver(pre_save, sender=CertificateOfAnalysis)
def _stash_coa_released(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_released = sender.all_objects.get(pk=instance.pk).released_to_customer
        except sender.DoesNotExist:
            instance._old_released = None
    else:
        instance._old_released = None


@receiver(post_save, sender=CertificateOfAnalysis)
def log_coa_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'qms_coa.created', instance, instance.tenant,
            meta={'coa_number': instance.coa_number},
        )
        return
    old = getattr(instance, '_old_released', None)
    if old is False and instance.released_to_customer:
        _tenant_audit(
            'qms_coa.released', instance, instance.tenant,
            meta={'coa_number': instance.coa_number,
                  'customer': instance.customer_name},
        )


# ---- NonConformanceReport ----

@receiver(pre_save, sender=NonConformanceReport)
def _stash_ncr_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=NonConformanceReport)
def log_ncr_save(sender, instance, created, **kwargs):
    if created:
        _tenant_audit(
            'qms_ncr.created', instance, instance.tenant,
            meta={'ncr_number': instance.ncr_number,
                  'severity': instance.severity,
                  'source': instance.source},
        )
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status:
        _tenant_audit(
            f'qms_ncr.{instance.status}', instance, instance.tenant,
            meta={'ncr_number': instance.ncr_number,
                  'from': old, 'to': instance.status},
        )


# ---- CorrectiveAction / PreventiveAction ----

@receiver(pre_save, sender=CorrectiveAction)
@receiver(pre_save, sender=PreventiveAction)
def _stash_action_status(sender, instance, **kwargs):
    _stash_status(instance, sender)


@receiver(post_save, sender=CorrectiveAction)
def log_ca_save(sender, instance, created, **kwargs):
    if created:
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status \
            and instance.status in ('completed', 'cancelled'):
        _tenant_audit(
            f'qms_ca.{instance.status}', instance, instance.tenant,
            meta={'ncr_number': instance.ncr.ncr_number,
                  'sequence': instance.sequence,
                  'from': old, 'to': instance.status},
        )


@receiver(post_save, sender=PreventiveAction)
def log_pa_save(sender, instance, created, **kwargs):
    if created:
        return
    old = getattr(instance, '_old_status', None)
    if old is not None and old != instance.status \
            and instance.status in ('completed', 'cancelled'):
        _tenant_audit(
            f'qms_pa.{instance.status}', instance, instance.tenant,
            meta={'ncr_number': instance.ncr.ncr_number,
                  'sequence': instance.sequence,
                  'from': old, 'to': instance.status},
        )


# ---- CalibrationRecord -> MeasurementEquipment side-effect ----

@receiver(post_save, sender=CalibrationRecord)
def _propagate_calibration_to_equipment(sender, instance, created, **kwargs):
    """Bump equipment.last_calibrated_at + next_due_at after a calibration is filed.

    Lesson L-15: compute the new next_due_at into a local first, then push it
    via update() - never read it back off the in-memory equipment variable.
    """
    if not created:
        return
    eq = instance.equipment
    new_last = instance.calibrated_at
    new_next = instance.next_due_at or (
        instance.calibrated_at + timedelta(days=eq.calibration_interval_days)
    )
    MeasurementEquipment.all_objects.filter(pk=eq.pk).update(
        last_calibrated_at=new_last,
        next_due_at=new_next,
    )
    _tenant_audit(
        'qms_calibration.created', instance, instance.tenant,
        meta={'record_number': instance.record_number,
              'equipment': eq.equipment_number,
              'result': instance.result},
    )
