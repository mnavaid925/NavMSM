"""Audit-log + cross-module signal wiring for Module 8.

Wires:
    - audit entries on Warehouse, GoodsReceiptNote, StockTransfer,
      StockAdjustment, CycleCountSheet status changes.
    - apps.mes.ProductionReport.post_save -> auto-emit StockMovement(production_in)
      so completed good qty hits inventory the moment the floor reports it.
    - apps.mes.ProductionReport.post_delete -> reverse the auto-emitted movement
      so the ledger stays balanced.

Auto-emit skips silently when the product has no default warehouse / bin
configured. We never block a floor save just because inventory isn't set up.
"""
import logging

from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from apps.core.models import get_current_tenant

from .models import (
    CycleCountSheet, GoodsReceiptNote, StockAdjustment, StockMovement,
    StockTransfer, Warehouse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------

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
            prev = sender.all_objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            instance._inv_prev_status = None
            return
        instance._inv_prev_status = getattr(prev, 'status', None)
    else:
        instance._inv_prev_status = None


# ---------------------------------------------------------------------------
# Warehouse (status-less, but audit creation + active toggle)
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=Warehouse)
def warehouse_pre_save(sender, instance, **_):
    if instance.pk:
        try:
            prev = sender.all_objects.get(pk=instance.pk)
            instance._inv_prev_active = prev.is_active
        except sender.DoesNotExist:
            instance._inv_prev_active = None
    else:
        instance._inv_prev_active = None


@receiver(post_save, sender=Warehouse)
def warehouse_post_save(sender, instance, created, **_):
    if created:
        _tenant_audit('inventory.warehouse.created', instance)
        return
    prev = getattr(instance, '_inv_prev_active', None)
    if prev is not None and prev != instance.is_active:
        _tenant_audit(
            'inventory.warehouse.active_changed',
            instance,
            meta={'from': prev, 'to': instance.is_active},
        )


# ---------------------------------------------------------------------------
# GoodsReceiptNote / StockTransfer / StockAdjustment / CycleCountSheet status
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=GoodsReceiptNote)
def grn_pre_save(sender, instance, **_):
    _stash_status(instance, sender)


@receiver(post_save, sender=GoodsReceiptNote)
def grn_post_save(sender, instance, created, **_):
    if created:
        _tenant_audit('inventory.grn.created', instance, meta={'status': instance.status})
        return
    prev = getattr(instance, '_inv_prev_status', None)
    if prev != instance.status:
        _tenant_audit(
            f'inventory.grn.{instance.status}',
            instance,
            meta={'from': prev, 'to': instance.status},
        )


@receiver(pre_save, sender=StockTransfer)
def transfer_pre_save(sender, instance, **_):
    _stash_status(instance, sender)


@receiver(post_save, sender=StockTransfer)
def transfer_post_save(sender, instance, created, **_):
    if created:
        _tenant_audit('inventory.transfer.created', instance, meta={'status': instance.status})
        return
    prev = getattr(instance, '_inv_prev_status', None)
    if prev != instance.status:
        _tenant_audit(
            f'inventory.transfer.{instance.status}',
            instance,
            meta={'from': prev, 'to': instance.status},
        )


@receiver(post_save, sender=StockAdjustment)
def adjustment_post_save(sender, instance, created, **_):
    if created:
        _tenant_audit(
            'inventory.adjustment.created', instance,
            meta={'reason': instance.reason, 'status': instance.status},
        )


@receiver(pre_save, sender=CycleCountSheet)
def cycle_count_pre_save(sender, instance, **_):
    _stash_status(instance, sender)


@receiver(post_save, sender=CycleCountSheet)
def cycle_count_post_save(sender, instance, created, **_):
    if created:
        _tenant_audit('inventory.cycle_count.created', instance, meta={'status': instance.status})
        return
    prev = getattr(instance, '_inv_prev_status', None)
    if prev != instance.status:
        _tenant_audit(
            f'inventory.cycle_count.{instance.status}',
            instance,
            meta={'from': prev, 'to': instance.status},
        )


# ---------------------------------------------------------------------------
# MES ProductionReport -> auto StockMovement (production_in / production_out)
# ---------------------------------------------------------------------------
#
# Wired lazily inside a function so this module loads even when MES isn't yet
# migrated (e.g. fresh checkout running `apps.inventory` migrations alone).

def _resolve_default_bin(tenant, product):
    """Return a default 'finished goods' bin for the product, or None.

    Strategy: pick the first non-blocked bin in the storage zone of the
    tenant's default warehouse. Returns None if no warehouse is flagged
    default — in which case the auto-emit is skipped silently.
    """
    from .models import StorageBin, Warehouse

    wh = (
        Warehouse.all_objects
        .filter(tenant=tenant, is_default=True, is_active=True)
        .first()
    )
    if wh is None:
        return None
    bin = (
        StorageBin.all_objects
        .filter(zone__warehouse=wh, zone__zone_type='storage', is_blocked=False)
        .order_by('zone__code', 'code')
        .first()
    )
    return bin


def _on_production_report_save(sender, instance, created, **_):
    """Auto-emit StockMovement(production_in) for good_qty.

    Skipped when:
        - the report wasn't just created (no auto-emit on edit)
        - good_qty is zero
        - the tenant has no default warehouse / suitable bin
        - a movement already references this report (idempotent guard)
    """
    if not created:
        return
    if not instance.good_qty or instance.good_qty <= 0:
        return

    if StockMovement.all_objects.filter(production_report=instance).exists():
        return

    tenant = getattr(instance, 'tenant', None)
    work_order = getattr(instance.work_order_operation, 'work_order', None) if instance.work_order_operation_id else None
    product = getattr(work_order, 'product', None) if work_order else None
    if tenant is None or product is None:
        return

    bin = _resolve_default_bin(tenant, product)
    if bin is None:
        logger.info(
            'inventory.auto_emit skipped: no default warehouse for tenant=%s product=%s',
            tenant.pk, product.pk,
        )
        return

    from .services.movements import post_movement
    try:
        post_movement(
            tenant=tenant,
            movement_type='production_in',
            product=product,
            qty=instance.good_qty,
            to_bin=bin,
            reason='auto: MES production report',
            reference=f'MES report #{instance.pk}',
            production_report=instance,
            posted_by=instance.reported_by,
        )
    except Exception:  # pragma: no cover - never block the floor
        logger.exception('inventory.auto_emit failed for report=%s', instance.pk)


def _on_production_report_delete(sender, instance, **_):
    """Reverse any auto-emitted movement when a report is deleted."""
    movements = StockMovement.all_objects.filter(production_report=instance)
    if not movements.exists():
        return
    from .services.movements import reverse_movement
    for mv in movements:
        try:
            reverse_movement(mv, reason='auto: MES report deleted')
        except Exception:  # pragma: no cover
            logger.exception(
                'inventory.auto_emit reversal failed for movement=%s', mv.pk
            )


def _wire_mes_signals():
    try:
        from apps.mes.models import ProductionReport
    except Exception:  # pragma: no cover
        logger.warning('inventory: apps.mes.ProductionReport unavailable; skipping wiring')
        return
    post_save.connect(
        _on_production_report_save,
        sender=ProductionReport,
        dispatch_uid='inventory_auto_production_in',
    )
    # pre_delete (not post_delete): on_delete=SET_NULL on StockMovement.production_report
    # clears the FK during deletion, so by the time post_delete fires we cannot
    # locate the movements anymore.
    pre_delete.connect(
        _on_production_report_delete,
        sender=ProductionReport,
        dispatch_uid='inventory_reverse_production_in',
    )


_wire_mes_signals()
