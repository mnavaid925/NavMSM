"""Service-layer tests for Module 18 - Returns & RMA.

Covers the pure-function helpers in apps/rma/services/.
"""
from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


def test_next_code_starts_at_one(tenant_a):
    from apps.rma.models import RMAReason
    from apps.rma.services.numbering import next_code
    assert next_code(RMAReason, tenant_a, 'X') == 'X-00001'


def test_next_code_pads_to_width(tenant_a, customer):
    from apps.rma.models import RMARequest
    from apps.rma.services.numbering import next_code
    RMARequest.objects.create(tenant=tenant_a, customer=customer)
    code = next_code(RMARequest, tenant_a, 'RMA')
    # Auto-increment ids are global across test, so we only assert format.
    assert code.startswith('RMA-') and len(code) == 9


# ---- warranty.add_months ----

def test_add_months_basic():
    from apps.rma.services.warranty import add_months
    assert add_months(date(2025, 1, 15), 12) == date(2026, 1, 15)
    assert add_months(date(2025, 1, 15), 0) == date(2025, 1, 15)


def test_add_months_handles_short_month_end():
    """31 Jan + 1 month -> 28/29 Feb, never 31 Feb."""
    from apps.rma.services.warranty import add_months
    out = add_months(date(2025, 1, 31), 1)
    assert out.month == 2 and out.day in (28, 29)


def test_compute_warranty_end_passes_through_to_add_months():
    from apps.rma.services.warranty import compute_warranty_end
    assert compute_warranty_end(date(2025, 6, 1), 6) == date(2025, 12, 1)


def test_is_under_warranty_within_range():
    from apps.rma.services.warranty import is_under_warranty
    assert is_under_warranty(date(2025, 1, 1), date(2025, 12, 31), date(2025, 6, 1)) is True
    assert is_under_warranty(date(2025, 1, 1), date(2025, 12, 31), date(2026, 1, 1)) is False


# ---- disposition.route_disposition ----

def test_route_disposition_categories():
    from apps.rma.services.disposition import (
        NONE, REPAIR_TICKET, RESTOCK, SUPPLIER_RETURN, route_disposition,
    )
    assert route_disposition('restock') == RESTOCK
    assert route_disposition('repair') == REPAIR_TICKET
    assert route_disposition('refurbish') == REPAIR_TICKET
    assert route_disposition('return_to_supplier') == SUPPLIER_RETURN
    assert route_disposition('scrap') == NONE
    assert route_disposition('quarantine') == NONE


# ---- repair.recompute_repair_costs ----

def test_recompute_repair_costs_aggregates_parts_and_labor(tenant_a, product):
    from apps.rma.models import RepairLaborLog, RepairOrder, RepairPartUsage
    from apps.rma.services.repair import recompute_repair_costs
    ro = RepairOrder.objects.create(tenant=tenant_a, product=product)
    RepairPartUsage.objects.create(
        tenant=tenant_a, repair_order=ro, part=product,
        quantity=Decimal('2'), unit_cost=Decimal('10'),
    )  # 20
    RepairLaborLog.objects.create(
        tenant=tenant_a, repair_order=ro,
        work_date=date.today(), minutes=60, hourly_rate=Decimal('45'),
    )  # 45
    # post_save signal already rolled up; explicit call must be idempotent.
    recompute_repair_costs(ro)
    ro.refresh_from_db()
    assert ro.actual_cost == Decimal('65.00')
    assert ro.labor_minutes == 60


# ---- chargeback.apply_transition ----

def test_chargeback_apply_transition_legal_path(tenant_a, supplier, product, customer, reason):
    from apps.rma.models import (
        ReturnAnalysis, RMALine, RMARequest, SupplierChargeback,
    )
    from apps.rma.services.chargeback import apply_transition
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
    apply_transition(cb, 'pending')
    cb.refresh_from_db()
    assert cb.status == 'pending'
    apply_transition(cb, 'issued')
    cb.refresh_from_db()
    assert cb.status == 'issued' and cb.issued_date is not None
    apply_transition(cb, 'recovered')
    cb.refresh_from_db()
    assert cb.status == 'recovered' and cb.recovered_date is not None


def test_chargeback_apply_transition_illegal_path_raises(
    tenant_a, supplier, product, customer, reason,
):
    """Skipping intermediate states must raise ValueError."""
    from apps.rma.models import (
        ReturnAnalysis, RMALine, RMARequest, SupplierChargeback,
    )
    from apps.rma.services.chargeback import apply_transition
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
    with pytest.raises(ValueError):
        apply_transition(cb, 'recovered')  # draft -> recovered is illegal
