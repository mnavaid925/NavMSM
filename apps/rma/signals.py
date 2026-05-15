"""Module 18 - Returns & RMA - cross-module signal handlers.

All handlers are module-level (strong reference - L-18 safe), carry a
`dispatch_uid`, and are idempotent on a natural key so a re-save never
double-emits.

  1. RMARequest.status='approved'
        -> draft rma.ReturnReceipt            (idempotent: one receipt per RMA)
  2. ReturnReceiptLine.disposition='restock'
        -> inventory.StockMovement(receipt)   (idempotent: disposition_done latch)
  3. ReturnReceiptLine.disposition in {repair, refurbish}
        -> draft rma.RepairOrder              (idempotent: disposition_done latch)
  4. RepairLaborLog.post_save
        -> labor.LaborBooking + repair cost rollup  (idempotent: labor_booking FK)
  5. RepairPartUsage.post_save / pre_delete
        -> repair cost rollup
  6. WarrantyClaim.status='approved' + resolution='replace'
        -> draft sales.SalesOrder             (idempotent: replacement_order FK)

Every side-effect is best-effort: a failure in the downstream module is
logged at WARNING (L-23) and swallowed so the RMA workflow never blocks
on another module's configuration.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# 1. RMARequest approved -> draft ReturnReceipt
# ----------------------------------------------------------------------------

@receiver(post_save, sender='rma.RMARequest', dispatch_uid='rma.approved_receipt')
def _rma_approved_draft_receipt(sender, instance, created, **kwargs):
    """When an RMA flips to approved, draft one ReturnReceipt for it.

    Idempotency key: at most one ReturnReceipt per RMARequest.
    """
    if instance.status != 'approved':
        return
    from apps.rma.models import ReturnReceipt

    if ReturnReceipt.all_objects.filter(rma=instance).exists():
        return
    try:
        with transaction.atomic():
            ReturnReceipt.objects.create(
                tenant=instance.tenant,
                rma=instance,
                status='draft',
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            'rma approved-receipt draft failed rma=%s err=%s',
            instance.code, exc, exc_info=True,
        )


# ----------------------------------------------------------------------------
# 2 + 3. ReturnReceiptLine disposition routing
# ----------------------------------------------------------------------------

@receiver(post_save, sender='rma.ReturnReceiptLine', dispatch_uid='rma.disposition_route')
def _receipt_line_route_disposition(sender, instance, created, **kwargs):
    """Route an inspected receipt line per its disposition.

    restock              -> inventory.StockMovement(receipt) into the warehouse
    repair / refurbish   -> draft rma.RepairOrder

    `disposition_done` is the idempotency latch; it is set via `.update()`
    (bypassing this signal) once the side-effect lands.
    """
    if instance.disposition_done:
        return
    from apps.rma.models import RepairOrder, ReturnReceiptLine
    from apps.rma.services.disposition import (
        REPAIR_TICKET, RESTOCK, route_disposition,
    )

    action = route_disposition(instance.disposition)

    if action == RESTOCK:
        qty = instance.quantity_received or 0
        if qty <= 0:
            return
        to_bin = _resolve_default_bin(instance.receipt.warehouse)
        if to_bin is None:
            # No warehouse / bin configured - leave the latch open so a
            # later edit (once a warehouse is set) can still route it.
            return
        try:
            from apps.inventory.services.movements import post_movement
            with transaction.atomic():
                mv = post_movement(
                    tenant=instance.tenant,
                    movement_type='receipt',
                    product=instance.rma_line.product,
                    qty=qty,
                    to_bin=to_bin,
                    reason='RMA restock',
                    reference=instance.receipt.code,
                )
                ReturnReceiptLine.all_objects.filter(pk=instance.pk).update(
                    stock_movement=mv, disposition_done=True,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                'rma restock movement failed receipt_line=%s err=%s',
                instance.pk, exc, exc_info=True,
            )
        return

    if action == REPAIR_TICKET:
        if RepairOrder.all_objects.filter(receipt_line=instance).exists():
            ReturnReceiptLine.all_objects.filter(pk=instance.pk).update(
                disposition_done=True,
            )
            return
        try:
            with transaction.atomic():
                RepairOrder.objects.create(
                    tenant=instance.tenant,
                    receipt_line=instance,
                    product=instance.rma_line.product,
                    order_type=(
                        'refurbishment' if instance.disposition == 'refurbish'
                        else 'repair'
                    ),
                    status='draft',
                    problem_description=(
                        instance.inspection_notes
                        or instance.rma_line.line_notes
                        or instance.rma_line.reason.name
                    ),
                )
                ReturnReceiptLine.all_objects.filter(pk=instance.pk).update(
                    disposition_done=True,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                'rma repair-order draft failed receipt_line=%s err=%s',
                instance.pk, exc, exc_info=True,
            )


# ----------------------------------------------------------------------------
# 4. RepairLaborLog -> labor.LaborBooking + cost rollup
# ----------------------------------------------------------------------------

@receiver(post_save, sender='rma.RepairLaborLog', dispatch_uid='rma.labor_booking')
def _repair_labor_emit_booking(sender, instance, created, **kwargs):
    """Mirror a repair labor log into a labor.LaborBooking and refresh the
    parent RepairOrder cost rollup.

    Idempotency key: RepairLaborLog.labor_booking FK. A booking is only
    emitted when an Employee is set (LaborBooking requires one).
    """
    from apps.rma.services.repair import recompute_repair_costs

    if instance.employee_id and not instance.labor_booking_id:
        try:
            from datetime import datetime, time

            from django.utils import timezone

            from apps.labor.models import LaborBooking
            from apps.rma.models import RepairLaborLog

            # LaborBooking.worked_at is a DateTimeField (downstream cost
            # signals call `.date()` on it) - lift our DateField to noon
            # on the work date in the active timezone.
            worked_at = timezone.make_aware(
                datetime.combine(instance.work_date, time(12, 0)),
            )
            with transaction.atomic():
                booking = LaborBooking.objects.create(
                    tenant=instance.tenant,
                    employee=instance.employee,
                    kind='indirect',
                    worked_at=worked_at,
                    minutes=instance.minutes,
                    hourly_rate_snapshot=instance.hourly_rate,
                    source_type='manual',
                    notes=f'RMA repair {instance.repair_order.code}',
                )
                RepairLaborLog.all_objects.filter(pk=instance.pk).update(
                    labor_booking=booking,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                'rma labor-booking emit failed labor_log=%s err=%s',
                instance.pk, exc, exc_info=True,
            )

    try:
        recompute_repair_costs(instance.repair_order)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            'rma repair cost rollup failed (labor) repair=%s err=%s',
            instance.repair_order_id, exc, exc_info=True,
        )


# ----------------------------------------------------------------------------
# 5. RepairPartUsage -> cost rollup
# ----------------------------------------------------------------------------

@receiver(post_save, sender='rma.RepairPartUsage', dispatch_uid='rma.part_rollup_save')
def _repair_part_rollup_on_save(sender, instance, created, **kwargs):
    from apps.rma.services.repair import recompute_repair_costs
    try:
        recompute_repair_costs(instance.repair_order)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            'rma repair cost rollup failed (part save) repair=%s err=%s',
            instance.repair_order_id, exc, exc_info=True,
        )


@receiver(pre_delete, sender='rma.RepairPartUsage', dispatch_uid='rma.part_rollup_delete')
def _repair_part_rollup_on_delete(sender, instance, **kwargs):
    """Refresh the rollup AFTER the row is gone via on_commit so the
    aggregate query no longer counts the deleted part.

    Skips silently when the parent RepairOrder itself was deleted in the
    same transaction (cascade) - there is nothing left to roll up onto.
    """
    from apps.rma.services.repair import recompute_repair_costs
    repair_order = instance.repair_order
    repair_pk = instance.repair_order_id

    def _recompute():
        from apps.rma.models import RepairOrder
        if not RepairOrder.all_objects.filter(pk=repair_pk).exists():
            return
        try:
            recompute_repair_costs(repair_order)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                'rma repair cost rollup failed (part delete) repair=%s err=%s',
                repair_pk, exc, exc_info=True,
            )

    transaction.on_commit(_recompute)


# ----------------------------------------------------------------------------
# 6. WarrantyClaim approved + replace -> draft sales.SalesOrder
# ----------------------------------------------------------------------------

@receiver(post_save, sender='rma.WarrantyClaim', dispatch_uid='rma.warranty_replacement_so')
def _warranty_claim_draft_replacement(sender, instance, created, **kwargs):
    """An approved warranty claim resolved by replacement drafts a zero-value
    replacement sales order for the registered customer.

    Idempotency key: WarrantyClaim.replacement_order FK.
    """
    if instance.status != 'approved' or instance.resolution != 'replace':
        return
    if instance.replacement_order_id:
        return
    try:
        from apps.sales.models import SalesOrder
        from apps.rma.models import WarrantyClaim
        with transaction.atomic():
            so = SalesOrder.objects.create(
                tenant=instance.tenant,
                customer=instance.registration.customer,
                status='draft',
                customer_po_number=f'WARRANTY-{instance.code}',
                created_by=instance.decided_by,
                notes=(
                    f'Auto-drafted warranty replacement for claim '
                    f'{instance.code} (registration {instance.registration.code}).'
                ),
            )
            WarrantyClaim.all_objects.filter(pk=instance.pk).update(
                replacement_order=so,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            'rma warranty-replacement SO draft failed claim=%s err=%s',
            instance.code, exc, exc_info=True,
        )


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _resolve_default_bin(warehouse):
    """Return a StorageBin to receive returned stock into, or None.

    Strategy: the first non-blocked storage bin in any zone of the
    warehouse. RMA restock is low-volume; a directed-putaway strategy can
    be layered on later if needed.
    """
    if warehouse is None:
        return None
    try:
        from apps.inventory.models import StorageBin
        return (
            StorageBin.objects.filter(zone__warehouse=warehouse, is_blocked=False)
            .order_by('id')
            .first()
        )
    except Exception:  # noqa: BLE001
        return None
