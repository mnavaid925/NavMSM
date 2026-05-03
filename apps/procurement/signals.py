"""Audit signals + cross-module event emission for Module 9.

Wires:
    - Audit entries on Supplier (create + is_approved toggle), PurchaseOrder,
      RequestForQuotation, SupplierQuotation, SupplierASN, SupplierInvoice,
      BlanketOrder, ScheduleRelease status transitions.
    - Cross-module hook: inventory.GoodsReceiptNote completed -> emit
      SupplierMetricEvent(po_received_on_time / po_received_late).
    - Cross-module hook: qms.IncomingInspection accepted/rejected -> emit
      SupplierMetricEvent(quality_pass / quality_fail).

Cross-module hooks live here (not in inventory/qms) so Module 9 owns its own
contract - removing the procurement app cleanly disables the events without
any orphan code in other apps.
"""
import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.core.models import get_current_tenant

from .models import (
    BlanketOrder,
    PurchaseOrder,
    QuotationAward,
    RequestForQuotation,
    ScheduleRelease,
    Supplier,
    SupplierASN,
    SupplierInvoice,
    SupplierMetricEvent,
    SupplierQuotation,
)

logger = logging.getLogger(__name__)


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


def _stash(instance, sender, *fields):
    if instance.pk:
        try:
            prev = sender.all_objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            prev = None
        for f in fields:
            setattr(instance, f'_proc_prev_{f}', getattr(prev, f, None) if prev else None)
    else:
        for f in fields:
            setattr(instance, f'_proc_prev_{f}', None)


# ---------------------------------------------------------------------------
# Supplier
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=Supplier)
def supplier_pre_save(sender, instance, **_):
    _stash(instance, sender, 'is_approved', 'is_active')


@receiver(post_save, sender=Supplier)
def supplier_post_save(sender, instance, created, **_):
    if created:
        _tenant_audit('procurement.supplier.created', instance, meta={'code': instance.code})
        return
    prev_app = getattr(instance, '_proc_prev_is_approved', None)
    if prev_app is not None and prev_app != instance.is_approved:
        _tenant_audit(
            'procurement.supplier.approval_changed',
            instance,
            meta={'from': prev_app, 'to': instance.is_approved},
        )


# ---------------------------------------------------------------------------
# Status-tracked resources
# ---------------------------------------------------------------------------

def _mk_status_signals(model, action_prefix):
    """Connect pre_save + post_save audit handlers for a status-tracked model.

    NOTE: pass weak=False to signal.connect() because the closure handlers
    defined inside this factory go out of scope after the function returns;
    the default weak-ref connection would let them be garbage-collected and
    the signals would never fire.
    """
    def _pre(sender, instance, **_):
        _stash(instance, sender, 'status')

    def _post(sender, instance, created, **_):
        if created:
            _tenant_audit(
                f'{action_prefix}.created', instance,
                meta={'status': instance.status},
            )
            return
        prev = getattr(instance, '_proc_prev_status', None)
        if prev != instance.status:
            _tenant_audit(
                f'{action_prefix}.{instance.status}',
                instance,
                meta={'from': prev, 'to': instance.status},
            )

    pre_save.connect(_pre, sender=model, weak=False, dispatch_uid=f'{action_prefix}_pre')
    post_save.connect(_post, sender=model, weak=False, dispatch_uid=f'{action_prefix}_post')


_mk_status_signals(PurchaseOrder, 'procurement.po')
_mk_status_signals(RequestForQuotation, 'procurement.rfq')
_mk_status_signals(SupplierQuotation, 'procurement.quotation')
_mk_status_signals(SupplierASN, 'procurement.asn')
_mk_status_signals(SupplierInvoice, 'procurement.invoice')
_mk_status_signals(BlanketOrder, 'procurement.blanket')
_mk_status_signals(ScheduleRelease, 'procurement.release')


@receiver(post_save, sender=QuotationAward)
def award_post_save(sender, instance, created, **_):
    if created:
        _tenant_audit(
            'procurement.rfq.awarded', instance,
            meta={'rfq': instance.rfq.rfq_number, 'quotation': instance.quotation.quote_number},
        )


# ---------------------------------------------------------------------------
# Cross-module hooks
# ---------------------------------------------------------------------------
#
# Wired lazily so the procurement app loads cleanly even when inventory/qms
# haven't migrated yet (e.g. fresh checkout).

def _stash_proc_prev(sender, instance, **_):
    """Store the previous-DB status on the instance under our own attr name.

    We don't rely on prev-status flags set by other apps' signals because the
    naming convention varies (inventory uses _inv_prev_status, qms uses
    _old_status). Owning our own snapshot keeps the procurement hook robust
    against refactors elsewhere.
    """
    if instance.pk:
        try:
            prev = sender.all_objects.get(pk=instance.pk)
            instance._proc_x_prev_status = getattr(prev, 'status', None)
        except sender.DoesNotExist:
            instance._proc_x_prev_status = None
    else:
        instance._proc_x_prev_status = None


def _on_grn_completed(sender, instance, created, **_):
    """Emit SupplierMetricEvent when a GoodsReceiptNote flips to 'completed'.

    Only emits when the GRN carries a `purchase_order` link AND was previously
    in a non-completed state. Silently skipped for legacy free-text GRNs.
    """
    prev = getattr(instance, '_proc_x_prev_status', None)
    if instance.status != 'completed' or prev == 'completed':
        return
    po = getattr(instance, 'purchase_order', None)
    if po is None:
        return
    on_time = True
    days_late = 0
    if po.required_date and instance.received_date:
        delta = (instance.received_date - po.required_date).days
        if delta > 0:
            on_time = False
            days_late = delta
    SupplierMetricEvent.all_objects.create(
        tenant=instance.tenant,
        supplier=po.supplier,
        event_type='po_received_on_time' if on_time else 'po_received_late',
        value=days_late,
        reference_type='inventory.GoodsReceiptNote',
        reference_id=str(instance.pk),
        notes=f'GRN {instance.grn_number}',
    )


def _on_iqc_decision(sender, instance, created, **_):
    """Emit SupplierMetricEvent on IQC accept / reject.

    Only emits on transitions to a final state, not on every save.
    """
    prev = getattr(instance, '_proc_x_prev_status', None)
    if prev == instance.status:
        return
    if instance.status not in ('accepted', 'rejected', 'accepted_with_deviation'):
        return
    sup = getattr(instance, 'supplier', None)
    if sup is None:
        return
    if instance.status == 'rejected':
        ev_type = 'quality_fail'
        value = 1
    else:
        ev_type = 'quality_pass'
        value = 0
    SupplierMetricEvent.all_objects.create(
        tenant=instance.tenant,
        supplier=sup,
        event_type=ev_type,
        value=value,
        reference_type='qms.IncomingInspection',
        reference_id=str(instance.pk),
        notes=f'IQC {getattr(instance, "iqc_number", instance.pk)}',
    )


def _wire_cross_module_signals():
    try:
        from apps.inventory.models import GoodsReceiptNote
        pre_save.connect(
            _stash_proc_prev,
            sender=GoodsReceiptNote,
            dispatch_uid='procurement_grn_prev',
        )
        post_save.connect(
            _on_grn_completed,
            sender=GoodsReceiptNote,
            dispatch_uid='procurement_grn_metric',
        )
    except Exception:  # pragma: no cover
        logger.warning('procurement: apps.inventory not loaded; skipping GRN hook')

    try:
        from apps.qms.models import IncomingInspection
        pre_save.connect(
            _stash_proc_prev,
            sender=IncomingInspection,
            dispatch_uid='procurement_iqc_prev',
        )
        post_save.connect(
            _on_iqc_decision,
            sender=IncomingInspection,
            dispatch_uid='procurement_iqc_metric',
        )
    except Exception:  # pragma: no cover
        logger.warning('procurement: apps.qms not loaded; skipping IQC hook')


_wire_cross_module_signals()
