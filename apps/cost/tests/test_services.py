"""Pure-function service coverage."""
from datetime import date
from decimal import Decimal

import pytest

from apps.cost import models as C
from apps.cost.services import (
    actual_costing as ac_svc,
    overhead as oh_svc,
    reporting as report_svc,
    standard_costing as std_svc,
    wip as wip_svc,
)


pytestmark = pytest.mark.django_db


# ---------- WIP service ----------

def test_post_wip_entry_bumps_denorm(acme, job):
    e = wip_svc.post_wip_entry(
        tenant=acme, job=job, entry_type='material_issued',
        amount=Decimal('100'),
    )
    job.refresh_from_db()
    assert job.total_material == Decimal('100.00')
    assert job.wip_balance == Decimal('100.00')
    assert e.entry_number == 'WIP-00001'


def test_post_wip_entry_completion_credits(acme, job):
    wip_svc.post_wip_entry(
        tenant=acme, job=job, entry_type='material_issued', amount=Decimal('100'),
    )
    wip_svc.post_wip_entry(
        tenant=acme, job=job, entry_type='completion', amount=Decimal('40'),
    )
    job.refresh_from_db()
    assert job.total_completion_credit == Decimal('40.00')
    assert job.wip_balance == Decimal('60.00')


def test_invalid_entry_type_raises(acme, job):
    with pytest.raises(ValueError):
        wip_svc.post_wip_entry(
            tenant=acme, job=job, entry_type='wrong', amount=Decimal('1'),
        )


def test_close_job_refuses_non_zero_balance(acme, job):
    wip_svc.post_wip_entry(
        tenant=acme, job=job, entry_type='material_issued', amount=Decimal('50'),
    )
    ok, msg = wip_svc.close_job(job)
    assert not ok
    assert '50' in msg


def test_close_job_with_force(acme, job):
    wip_svc.post_wip_entry(
        tenant=acme, job=job, entry_type='material_issued', amount=Decimal('50'),
    )
    ok, _ = wip_svc.close_job(job, force=True)
    assert ok
    job.refresh_from_db()
    assert job.status == 'closed'


def test_close_job_zero_balance(acme, job):
    wip_svc.post_wip_entry(
        tenant=acme, job=job, entry_type='material_issued', amount=Decimal('100'),
    )
    wip_svc.post_wip_entry(
        tenant=acme, job=job, entry_type='completion', amount=Decimal('100'),
    )
    ok, _ = wip_svc.close_job(job)
    assert ok


def test_close_already_closed_idempotent(acme, job):
    job.status = 'closed'
    job.save()
    ok, _ = wip_svc.close_job(job)
    assert ok


def test_reverse_wip_entry(acme, job):
    e = wip_svc.post_wip_entry(
        tenant=acme, job=job, entry_type='material_issued', amount=Decimal('100'),
    )
    rev = wip_svc.reverse_wip_entry(e)
    assert rev.is_reversal
    assert rev.amount == Decimal('-100.00')


def test_compute_operation_rollup(acme, job):
    wip_svc.post_wip_entry(
        tenant=acme, job=job, entry_type='material_issued', amount=Decimal('100'),
    )
    wip_svc.post_wip_entry(
        tenant=acme, job=job, entry_type='labor_applied', amount=Decimal('50'),
    )
    rollup = wip_svc.compute_operation_rollup(job)
    # All entries lacked routing_operation -> single bucket.
    assert len(rollup) == 1
    bucket = rollup[0]
    assert bucket['material'] == Decimal('100')
    assert bucket['labor'] == Decimal('50')


# ---------- Overhead service ----------

def test_compute_rate_pure():
    assert oh_svc.compute_rate(Decimal('1000'), Decimal('100')) == Decimal('10.000000')
    assert oh_svc.compute_rate(Decimal('500'), Decimal('0')) == Decimal('0')


def test_apply_overhead_creates_allocations(acme, acp_open, pool, driver, overhead_rate, production_order, job):
    C.DriverActuals.objects.create(
        tenant=acme, driver=driver, period=acp_open,
        production_order=production_order, quantity=Decimal('20'),
    )
    counts = oh_svc.apply_overhead(acp_open)
    assert counts['allocations'] == 1
    assert counts['wip_entries'] == 1
    alloc = C.OverheadAllocation.objects.filter(tenant=acme).first()
    assert alloc.applied_amount == Decimal('200.00')


def test_apply_overhead_idempotent(acme, acp_open, pool, driver, overhead_rate, production_order, job):
    C.DriverActuals.objects.create(
        tenant=acme, driver=driver, period=acp_open,
        production_order=production_order, quantity=Decimal('20'),
    )
    oh_svc.apply_overhead(acp_open)
    oh_svc.apply_overhead(acp_open)  # rerun
    # Re-running clears prior + re-emits, so still 1 allocation
    assert C.OverheadAllocation.objects.filter(tenant=acme, is_reversed=False).count() == 1


def test_apply_overhead_refuses_closed(acme, acp_closed):
    with pytest.raises(ValueError):
        oh_svc.apply_overhead(acp_closed)


def test_reverse_overhead_marks_reversed(acme, acp_open, pool, driver, overhead_rate, production_order, job):
    C.DriverActuals.objects.create(
        tenant=acme, driver=driver, period=acp_open,
        production_order=production_order, quantity=Decimal('5'),
    )
    oh_svc.apply_overhead(acp_open)
    oh_svc.reverse_overhead(acp_open, reason='test')
    assert C.OverheadAllocation.objects.filter(tenant=acme, is_reversed=True).count() == 1


def test_accumulate_indirect_labor(acme, acp_open, pool):
    actual = oh_svc.accumulate_indirect_labor(acp_open, pool, Decimal('100'))
    assert actual.actual_amount == Decimal('100.00')
    actual = oh_svc.accumulate_indirect_labor(acp_open, pool, Decimal('50'))
    assert actual.actual_amount == Decimal('150.00')


# ---------- Actual costing service ----------

def test_compute_actual_returns_actualcost(acme, production_order, job):
    wip_svc.post_wip_entry(
        tenant=acme, job=job, entry_type='material_issued', amount=Decimal('100'),
    )
    wip_svc.post_wip_entry(
        tenant=acme, job=job, entry_type='labor_applied', amount=Decimal('50'),
    )
    ac = ac_svc.compute_actual(production_order)
    assert ac.material_cost == Decimal('100')
    assert ac.labor_cost == Decimal('50')
    assert ac.total_cost == Decimal('150')


def test_compute_variances_returns_dict(acme, production_order, cost_version, standard_cost, job):
    wip_svc.post_wip_entry(
        tenant=acme, job=job, entry_type='material_issued', amount=Decimal('250'),
    )
    v = ac_svc.compute_variances(production_order, version=cost_version)
    assert v is not None
    # std material = 20*10 = 200; actual = 250; diff = 50
    # split 60/40 -> price=30, usage=20
    assert v['material_price_variance'] == Decimal('30.00')


def test_compute_variances_returns_none_without_std(acme, production_order, cost_version):
    # cost_version exists but no StandardCost row -> None
    v = ac_svc.compute_variances(production_order, version=cost_version)
    assert v is None


# ---------- Standard costing service ----------

def test_compare_versions_diff(acme):
    v1 = C.StandardCostVersion.objects.create(
        tenant=acme, name='V1', effective_from=date(2026, 1, 1),
    )
    v2 = C.StandardCostVersion.objects.create(
        tenant=acme, name='V2', effective_from=date(2026, 2, 1),
    )
    from apps.plm.models import Product, ProductCategory
    cat = ProductCategory.objects.create(tenant=acme, code='C', name='Cat')
    p = Product.objects.create(
        tenant=acme, sku='X', name='X', category=cat,
        product_type='finished_good', unit_of_measure='ea',
    )
    C.StandardCost.objects.create(
        tenant=acme, version=v1, product=p, material_cost=Decimal('10'),
    )
    C.StandardCost.objects.create(
        tenant=acme, version=v2, product=p, material_cost=Decimal('15'),
    )
    rows = std_svc.compare_versions(v1, v2)
    assert len(rows) == 1
    assert rows[0]['delta'] == Decimal('5.0000')


# ---------- Reporting service ----------

def test_generate_cogm(acme, acp_closed, production_order, job):
    # Need entries within the closed period
    from django.utils import timezone
    e = wip_svc.post_wip_entry(
        tenant=acme, job=job, entry_type='material_issued', amount=Decimal('100'),
    )
    # backdate
    e.entry_date = timezone.make_aware(timezone.datetime(2025, 12, 15, 0, 0))
    e.save(update_fields=['entry_date'])

    report = report_svc.generate_cogm(acp_closed)
    assert report.direct_materials == Decimal('100')


def test_generate_plant_pnl(acme, acp_closed):
    report = report_svc.generate_plant_pnl(
        acp_closed, selling_expense=Decimal('100'),
        ga_expense=Decimal('50'), unallocated_overhead=Decimal('10'),
    )
    assert report.selling_expense == Decimal('100')
