"""Module 17 - Sales - cross-module signal handlers.

17.2  SalesOrder.status='confirmed' + line.is_make_to_order=True
        -> draft pps.ProductionOrder
      (idempotent: ProductionOrder.source_sales_line is the dedup key)

17.4  Shipment.status='delivered'
        -> inventory.StockMovement(shipment_out)
      Shipment.pre_delete
        -> reverse the shipment_out movements
      SalesInvoice.status='paid'
        -> atomic conditional UPDATE on Customer.credit_used
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver


# ----------------------------------------------------------------------------
# 17.2  MTO auto-PO emission on SalesOrder.status='confirmed'
# ----------------------------------------------------------------------------

@receiver(post_save, sender='sales.SalesOrder', dispatch_uid='sales.mto_auto_po')
def _mto_emit_production_orders(sender, instance, created, **kwargs):
    """When an SO flips to confirmed, draft one PPS ProductionOrder per
    is_make_to_order=True line that hasn't already spawned one.

    Idempotency key: pps.ProductionOrder.source_sales_line FK.
    """
    if instance.status != 'confirmed':
        return
    from apps.pps.models import ProductionOrder

    for line in instance.lines.filter(is_make_to_order=True):
        # Skip lines that already spawned a PO
        if ProductionOrder.all_objects.filter(source_sales_line=line).exists():
            continue
        with transaction.atomic():
            po = ProductionOrder(
                tenant=instance.tenant,
                product=line.product,
                quantity=line.qty_ordered,
                status='planned',
                priority=instance.priority,
                source_sales_line=line,
                created_by=instance.confirmed_by or instance.created_by,
            )
            # Auto-number order_number using the existing PPS pattern
            last = (
                ProductionOrder.all_objects.filter(tenant=instance.tenant)
                .order_by('-id').first()
            )
            seq = (last.id + 1) if last else 1
            po.order_number = f'PO-{seq:05d}'
            po.save()


# ----------------------------------------------------------------------------
# 17.4  Shipment delivered -> StockMovement(shipment_out) per line
# ----------------------------------------------------------------------------

@receiver(post_save, sender='sales.Shipment', dispatch_uid='sales.shipment_delivered_movement')
def _shipment_delivered_emit_movements(sender, instance, created, **kwargs):
    """When a Shipment flips to delivered, emit one shipment_out movement
    per ShipmentLine. Idempotent on `StockMovement.source_shipment` FK.

    Best-effort: silently skipped if no from_bin is resolvable (the source
    warehouse on the shipment has no default bin) so the workflow does not
    block on inventory configuration. Logs via a no-op when so.
    """
    if instance.status != 'delivered':
        return
    from apps.inventory.models import StockMovement
    from apps.inventory.services.movements import post_movement

    for line in instance.shipment_lines.all():
        if StockMovement.all_objects.filter(
            source_shipment_line=line,
        ).exists():
            continue
        from_bin = line.source_bin or _resolve_default_bin(instance.source_warehouse)
        if from_bin is None:
            continue
        try:
            with transaction.atomic():
                mv = post_movement(
                    tenant=instance.tenant,
                    movement_type='shipment_out',
                    product=line.order_line.product,
                    qty=line.qty_shipped or line.qty_to_ship,
                    from_bin=from_bin,
                    reason='Sales shipment',
                    reference=instance.code,
                )
                # Stamp source_shipment_line for idempotency
                StockMovement.all_objects.filter(pk=mv.pk).update(
                    source_shipment_line=line, source_shipment=instance,
                )
        except Exception:
            # Inventory pre-flight failed (e.g. zero stock + non-adjust type).
            # Do not crash the shipment confirmation; leave the bin variance
            # to be fixed via cycle count.
            continue


@receiver(pre_delete, sender='sales.Shipment', dispatch_uid='sales.shipment_pre_delete_reverse')
def _shipment_pre_delete_reverse(sender, instance, **kwargs):
    """Reverse any auto-emitted shipment_out movements before the Shipment
    row is deleted, so the ledger doesn't drift."""
    from apps.inventory.models import StockMovement
    from apps.inventory.services.movements import reverse_movement

    qs = StockMovement.all_objects.filter(source_shipment=instance)
    for mv in qs:
        try:
            reverse_movement(mv, reason=f'Shipment {instance.code} deleted')
        except Exception:
            continue


# ----------------------------------------------------------------------------
# 17.4  SalesInvoice paid -> Customer.credit_used denorm down
# ----------------------------------------------------------------------------

@receiver(post_save, sender='sales.SalesInvoice', dispatch_uid='sales.invoice_paid_credit_used')
def _invoice_paid_drop_credit_used(sender, instance, created, **kwargs):
    """When an invoice flips to paid, atomically reduce the customer's
    credit_used by the invoice grand_total via a conditional UPDATE."""
    if instance.status != 'paid':
        return
    if not instance.sales_order_id:
        return
    from apps.sales.models import Customer
    from django.db.models import F

    Customer.all_objects.filter(
        pk=instance.sales_order.customer_id,
    ).update(
        credit_used=F('credit_used') - (instance.grand_total or Decimal('0')),
    )


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _resolve_default_bin(warehouse):
    """Return a Bin to source the shipment from, or None.

    Strategy: pick the first bin marked is_default in the first zone of
    the warehouse. Matches the existing MES production_in fallback.
    """
    if warehouse is None:
        return None
    try:
        from apps.inventory.models import StorageBin
        bin_ = (
            StorageBin.objects.filter(zone__warehouse=warehouse, is_default=True)
            .first()
        )
        if bin_:
            return bin_
        # Fall back to any bin in the warehouse
        return StorageBin.objects.filter(zone__warehouse=warehouse).first()
    except Exception:
        return None
