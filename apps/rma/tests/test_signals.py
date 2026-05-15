"""Cross-module signal hook tests for Module 18 - Returns & RMA.

Each handler is verified for (a) firing under its trigger and (b) being
idempotent on re-save (no duplicate side-effect).
"""
from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db


def test_rma_approval_drafts_return_receipt(tenant_a, rma_request):
    """RMARequest.status='approved' -> ReturnReceipt(draft). Idempotent."""
    from apps.rma.models import ReturnReceipt
    rma_request.status = 'approved'
    rma_request.save()
    assert ReturnReceipt.objects.filter(rma=rma_request).count() == 1
    # Re-save (e.g. note edit) must NOT spawn another.
    rma_request.internal_notes = 'edit'
    rma_request.save()
    assert ReturnReceipt.objects.filter(rma=rma_request).count() == 1


def test_restock_disposition_emits_inventory_movement(
    tenant_a, rma_request, warehouse_with_bin,
):
    """Restock disposition -> inventory.StockMovement; latch + FK set."""
    from apps.inventory.models import StockMovement
    from apps.rma.models import ReturnReceipt, ReturnReceiptLine
    wh, _bin = warehouse_with_bin
    rma_request.status = 'approved'
    rma_request.save()
    receipt = ReturnReceipt.objects.get(rma=rma_request)
    receipt.warehouse = wh
    receipt.save(update_fields=['warehouse'])
    line = ReturnReceiptLine.objects.create(
        tenant=tenant_a, receipt=receipt, rma_line=rma_request.lines.first(),
        quantity_received=Decimal('2'),
        condition_assessed='like_new', disposition='restock',
    )
    line.refresh_from_db()
    assert line.disposition_done is True
    assert line.stock_movement_id is not None
    mv = StockMovement.objects.get(pk=line.stock_movement_id)
    assert mv.movement_type == 'receipt'
    # Re-save must not emit a second movement.
    before = StockMovement.objects.filter(rma_receipt_lines=line).count()
    line.inspection_notes = 'edit'
    line.save()
    assert StockMovement.objects.filter(rma_receipt_lines=line).count() == before


def test_repair_disposition_drafts_repair_order(tenant_a, rma_request):
    """Repair / refurbish disposition -> RepairOrder; idempotent."""
    from apps.rma.models import RepairOrder, ReturnReceipt, ReturnReceiptLine
    rma_request.status = 'approved'
    rma_request.save()
    receipt = ReturnReceipt.objects.get(rma=rma_request)
    line = ReturnReceiptLine.objects.create(
        tenant=tenant_a, receipt=receipt, rma_line=rma_request.lines.first(),
        quantity_received=Decimal('1'),
        condition_assessed='defective', disposition='repair',
    )
    line.refresh_from_db()
    assert line.disposition_done is True
    assert RepairOrder.objects.filter(receipt_line=line).count() == 1
    # Re-save the line - no duplicate RepairOrder.
    line.inspection_notes = 'edit'
    line.save()
    assert RepairOrder.objects.filter(receipt_line=line).count() == 1


def test_repair_labor_log_emits_labor_booking(tenant_a, product, employee):
    """RepairLaborLog with an Employee mirrors a labor.LaborBooking."""
    from apps.labor.models import LaborBooking
    from apps.rma.models import RepairLaborLog, RepairOrder
    ro = RepairOrder.objects.create(tenant=tenant_a, product=product)
    log = RepairLaborLog.objects.create(
        tenant=tenant_a, repair_order=ro, employee=employee,
        work_date=date.today(), minutes=90, hourly_rate=Decimal('40'),
    )
    log.refresh_from_db()
    assert log.labor_booking_id is not None
    booking = LaborBooking.objects.get(pk=log.labor_booking_id)
    assert booking.kind == 'indirect'
    assert booking.minutes == 90
    # Re-save log - the existing booking FK prevents a second create.
    log.notes = 'edit'
    log.save()
    log.refresh_from_db()
    assert LaborBooking.objects.filter(pk=log.labor_booking_id).count() == 1


def test_repair_labor_log_recomputes_repair_cost(tenant_a, product):
    """RepairLaborLog save updates RepairOrder.actual_cost + labor_minutes."""
    from apps.rma.models import RepairLaborLog, RepairOrder
    ro = RepairOrder.objects.create(tenant=tenant_a, product=product)
    RepairLaborLog.objects.create(
        tenant=tenant_a, repair_order=ro,
        work_date=date.today(), minutes=120, hourly_rate=Decimal('30'),
    )
    ro.refresh_from_db()
    assert ro.actual_cost == Decimal('60.00')
    assert ro.labor_minutes == 120


@pytest.mark.django_db(transaction=True)
def test_repair_part_usage_recomputes_repair_cost(tenant_a, product):
    """RepairPartUsage save/delete refreshes RepairOrder.actual_cost.

    Uses transaction=True so the pre_delete `transaction.on_commit`
    recompute callback actually fires - the default test transaction
    wrap suppresses on_commit.
    """
    from apps.rma.models import RepairOrder, RepairPartUsage
    ro = RepairOrder.objects.create(tenant=tenant_a, product=product)
    p = RepairPartUsage.objects.create(
        tenant=tenant_a, repair_order=ro, part=product,
        quantity=Decimal('2'), unit_cost=Decimal('15'),
    )
    ro.refresh_from_db()
    assert ro.actual_cost == Decimal('30.00')
    p.delete()
    ro.refresh_from_db()
    assert ro.actual_cost == Decimal('0.00')


def test_warranty_claim_approved_replace_drafts_sales_order(
    tenant_a, product, customer, policy,
):
    """Approved warranty claim w/ resolution='replace' drafts a sales.SalesOrder."""
    from apps.rma.models import WarrantyClaim, WarrantyRegistration
    from apps.sales.models import SalesOrder
    reg = WarrantyRegistration.objects.create(
        tenant=tenant_a, product=product, customer=customer, policy=policy,
        purchase_date=date.today(), start_date=date.today(),
    )
    claim = WarrantyClaim.objects.create(
        tenant=tenant_a, registration=reg, status='submitted', resolution='replace',
    )
    assert claim.replacement_order_id is None
    claim.status = 'approved'
    claim.decided_at = timezone.now()
    claim.save()
    claim.refresh_from_db()
    assert claim.replacement_order_id is not None
    so = SalesOrder.objects.get(pk=claim.replacement_order_id)
    assert so.status == 'draft'
    assert so.customer_id == customer.id
    # Idempotent: re-save claim must NOT draft another SO.
    claim.save()
    claim.refresh_from_db()
    assert SalesOrder.objects.filter(
        tenant=tenant_a, customer_po_number=f'WARRANTY-{claim.code}',
    ).count() == 1


def test_warranty_claim_repair_resolution_no_sales_order(
    tenant_a, product, customer, policy,
):
    """Approved 'repair' resolution must NOT draft a sales order."""
    from apps.rma.models import WarrantyClaim, WarrantyRegistration
    reg = WarrantyRegistration.objects.create(
        tenant=tenant_a, product=product, customer=customer, policy=policy,
        purchase_date=date.today(), start_date=date.today(),
    )
    claim = WarrantyClaim.objects.create(
        tenant=tenant_a, registration=reg, status='approved', resolution='repair',
    )
    claim.refresh_from_db()
    assert claim.replacement_order_id is None
