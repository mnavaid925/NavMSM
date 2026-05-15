"""Model-level tests for Module 18 - Returns & RMA Management.

Covers:
    * Auto-numbering on save() for every prefixed model.
    * Computed fields (RepairLaborLog.labor_cost, RepairPartUsage.line_cost,
      WarrantyRegistration.end_date).
    * Decimal validators reject negative quantities.
    * Workflow helper methods (is_editable / can_submit / can_approve / ...).
    * `unique_together(tenant, name)` is enforced on tenant catalogs.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

pytestmark = pytest.mark.django_db


def test_rma_request_auto_numbering(tenant_a, customer):
    from apps.rma.models import RMARequest
    r1 = RMARequest.objects.create(tenant=tenant_a, customer=customer)
    r2 = RMARequest.objects.create(tenant=tenant_a, customer=customer)
    assert r1.code.startswith('RMA-') and len(r1.code) == 9
    assert r1.code != r2.code


def test_return_receipt_auto_numbering(tenant_a, rma_request):
    from apps.rma.models import ReturnReceipt
    rr = ReturnReceipt.objects.create(tenant=tenant_a, rma=rma_request)
    assert rr.code.startswith('RR-')


def test_repair_order_auto_numbering(tenant_a, product):
    from apps.rma.models import RepairOrder
    ro = RepairOrder.objects.create(tenant=tenant_a, product=product)
    assert ro.code.startswith('REP-')


def test_warranty_policy_auto_numbering(tenant_a):
    from apps.rma.models import WarrantyPolicy
    p = WarrantyPolicy.objects.create(
        tenant=tenant_a, name='X', coverage_type='full', duration_months=24,
    )
    assert p.code.startswith('WP-')


def test_warranty_registration_end_date_computed(tenant_a, product, customer, policy):
    """end_date = start_date + policy.duration_months (12mo policy)."""
    from apps.rma.models import WarrantyRegistration
    reg = WarrantyRegistration.objects.create(
        tenant=tenant_a, product=product, customer=customer, policy=policy,
        purchase_date=date(2025, 1, 15), start_date=date(2025, 1, 15),
    )
    assert reg.end_date == date(2026, 1, 15)


def test_warranty_registration_is_expiring_soon_flag(tenant_a, product, customer):
    """Active registration with end_date within 30 days flags expiring_soon."""
    from apps.rma.models import WarrantyPolicy, WarrantyRegistration
    # 1-month policy purchased 11 days ago -> ends in ~20 days
    pol = WarrantyPolicy.objects.create(
        tenant=tenant_a, name='1m', coverage_type='parts', duration_months=1,
    )
    today = date.today()
    reg = WarrantyRegistration.objects.create(
        tenant=tenant_a, product=product, customer=customer, policy=pol,
        purchase_date=today - timedelta(days=11),
        start_date=today - timedelta(days=11),
    )
    assert reg.is_expiring_soon is True
    assert 0 <= reg.days_remaining <= 30


def test_repair_part_usage_line_cost_computed(tenant_a, product):
    """RepairPartUsage.line_cost = quantity * unit_cost, set in save()."""
    from apps.rma.models import RepairOrder, RepairPartUsage
    ro = RepairOrder.objects.create(tenant=tenant_a, product=product)
    p = RepairPartUsage.objects.create(
        tenant=tenant_a, repair_order=ro, part=product,
        quantity=Decimal('3'), unit_cost=Decimal('12.50'),
    )
    assert p.line_cost == Decimal('37.50')


def test_repair_labor_log_labor_cost_computed(tenant_a, product):
    """RepairLaborLog.labor_cost = minutes/60 * hourly_rate, set in save()."""
    from apps.rma.models import RepairLaborLog, RepairOrder
    ro = RepairOrder.objects.create(tenant=tenant_a, product=product)
    log = RepairLaborLog.objects.create(
        tenant=tenant_a, repair_order=ro,
        work_date=date.today(), minutes=120, hourly_rate=Decimal('30.00'),
    )
    # 120/60 * 30 = 60.00
    assert log.labor_cost == Decimal('60.00')


def test_rma_line_auto_line_no(tenant_a, customer, product, reason):
    """Adding multiple lines increments line_no monotonically per RMA."""
    from apps.rma.models import RMALine, RMARequest
    rma = RMARequest.objects.create(tenant=tenant_a, customer=customer)
    l1 = RMALine.objects.create(
        tenant=tenant_a, rma=rma, product=product, quantity=Decimal('1'),
        unit_price=Decimal('1'), reason=reason, condition_reported='used',
    )
    l2 = RMALine.objects.create(
        tenant=tenant_a, rma=rma, product=product, quantity=Decimal('1'),
        unit_price=Decimal('1'), reason=reason, condition_reported='used',
    )
    assert l1.line_no == 1 and l2.line_no == 2
    # Editing line 1 must NOT bump its line_no.
    l1.refresh_from_db()
    l1.quantity = Decimal('5')
    l1.save()
    l1.refresh_from_db()
    assert l1.line_no == 1


def test_rma_request_workflow_helpers(tenant_a, rma_request):
    assert rma_request.is_editable() is True
    assert rma_request.can_submit() is True  # has 1 line
    assert rma_request.can_approve() is False  # still draft
    assert rma_request.can_cancel() is True


def test_repair_order_workflow_helpers(tenant_a, product):
    from apps.rma.models import RepairOrder
    ro = RepairOrder.objects.create(tenant=tenant_a, product=product)
    assert ro.can_start() is True
    ro.status = 'in_progress'
    assert ro.can_hold() is True and ro.can_complete() is True
    ro.status = 'completed'
    assert ro.can_cancel() is False


def test_rma_reason_unique_per_tenant(tenant_a):
    from apps.rma.models import RMAReason
    RMAReason.objects.create(tenant=tenant_a, name='Dup', category='other')
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            RMAReason.objects.create(tenant=tenant_a, name='Dup', category='other')


def test_negative_quantity_rejected_by_validators(tenant_a, rma_request, product, reason):
    from apps.rma.models import RMALine
    line = RMALine(
        tenant=tenant_a, rma=rma_request, product=product, reason=reason,
        quantity=Decimal('-1'), unit_price=Decimal('10'),
        condition_reported='defective',
    )
    with pytest.raises(ValidationError):
        line.full_clean()


def test_chargeback_str_uses_code(tenant_a, supplier, product, customer, reason):
    from apps.rma.models import (
        ReturnAnalysis, RMALine, RMARequest, SupplierChargeback,
    )
    rma = RMARequest.objects.create(tenant=tenant_a, customer=customer)
    line = RMALine.objects.create(
        tenant=tenant_a, rma=rma, product=product, reason=reason,
        quantity=Decimal('1'), unit_price=Decimal('1'),
        condition_reported='defective',
    )
    analysis = ReturnAnalysis.objects.create(tenant=tenant_a, rma_line=line)
    cb = SupplierChargeback.objects.create(
        tenant=tenant_a, analysis=analysis, supplier=supplier,
        amount=Decimal('100'),
    )
    assert cb.code.startswith('SCB-')
    assert cb.code in str(cb)
