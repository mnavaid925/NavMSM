"""Model invariants + auto-numbering + denorm computations."""
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.cost import models as C


pytestmark = pytest.mark.django_db


# ---------- Auto-numbering ----------

def test_standard_cost_version_auto_number(acme):
    v = C.StandardCostVersion.objects.create(
        tenant=acme, name='V1', effective_from=date(2026, 1, 1),
    )
    assert v.version_number == 'SCV-00001'
    v2 = C.StandardCostVersion.objects.create(
        tenant=acme, name='V2', effective_from=date(2026, 2, 1),
    )
    assert v2.version_number == 'SCV-00002'


def test_accounting_period_auto_number(acme):
    p = C.AccountingPeriod.objects.create(
        tenant=acme, name='Jan', start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
    )
    assert p.period_number == 'ACP-00001'


def test_overhead_allocation_auto_number(acme, pool, acp_open, driver):
    a = C.OverheadAllocation.objects.create(
        tenant=acme, pool=pool, period=acp_open,
        driver_qty=Decimal('1'), rate_applied=Decimal('1'),
    )
    assert a.allocation_number == 'OHA-00001'


def test_jobcost_auto_number(acme, production_order):
    j = C.JobCost.objects.create(tenant=acme, production_order=production_order)
    assert j.job_number == 'JC-00001'


def test_cogm_auto_number(acme, acp_closed):
    r = C.COGMReport.objects.create(tenant=acme, period=acp_closed)
    assert r.report_number == 'COGM-00001'


def test_variance_auto_number(acme, production_order, cost_version):
    v = C.CostVariance.objects.create(
        tenant=acme, production_order=production_order, version=cost_version,
    )
    assert v.variance_number == 'VAR-00001'


def test_wip_entry_auto_number(acme, job):
    e = C.WIPEntry.objects.create(
        tenant=acme, job=job, entry_type='material_issued',
        amount=Decimal('100'),
    )
    assert e.entry_number == 'WIP-00001'


# ---------- Denorm computations ----------

def test_standard_cost_total_recomputed_on_save(acme, cost_version, product):
    sc = C.StandardCost.objects.create(
        tenant=acme, version=cost_version, product=product,
        material_cost=Decimal('10'), labor_cost=Decimal('5'),
        overhead_cost=Decimal('3'), tooling_cost=Decimal('1'),
    )
    assert sc.total_cost == Decimal('19.0000')


def test_overhead_rate_per_unit_recomputed(acme, pool, acp_open, driver):
    r = C.OverheadRate.objects.create(
        tenant=acme, pool=pool, period=acp_open, driver=driver,
        budgeted_amount=Decimal('500'), budgeted_driver_qty=Decimal('50'),
    )
    assert r.rate_per_driver_unit == Decimal('10.000000')


def test_overhead_allocation_applied_amount(acme, pool, acp_open, driver):
    a = C.OverheadAllocation.objects.create(
        tenant=acme, pool=pool, period=acp_open,
        driver_qty=Decimal('5'), rate_applied=Decimal('20'),
    )
    assert a.applied_amount == Decimal('100.00')


def test_cogm_recomputes(acme, acp_closed):
    r = C.COGMReport.objects.create(
        tenant=acme, period=acp_closed,
        opening_wip=Decimal('100'), direct_materials=Decimal('200'),
        direct_labor=Decimal('150'), overhead_applied=Decimal('50'),
        closing_wip=Decimal('80'),
    )
    assert r.cogm == Decimal('420.00')  # 100+200+150+50-80


def test_jobcost_balance_recomputes(acme, production_order):
    j = C.JobCost.objects.create(
        tenant=acme, production_order=production_order,
        total_material=Decimal('100'), total_labor=Decimal('50'),
        total_overhead=Decimal('30'), total_completion_credit=Decimal('20'),
    )
    assert j.wip_balance == Decimal('160.00')  # 100+50+30-20


def test_margin_recomputes(acme, acp_open, product):
    m = C.GrossMarginReport.objects.create(
        tenant=acme, period=acp_open, product=product,
        units_completed=Decimal('10'), unit_sale_price=Decimal('20'),
        actual_cost_per_unit=Decimal('12'),
    )
    assert m.revenue == Decimal('200.00')
    assert m.cogs == Decimal('120.00')
    assert m.gross_margin == Decimal('80.00')
    assert m.margin_percent == Decimal('40.00')


def test_pnl_recomputes(acme, acp_closed):
    p = C.PlantPnLReport.objects.create(
        tenant=acme, period=acp_closed,
        revenue=Decimal('1000'), cogm=Decimal('600'),
        selling_expense=Decimal('100'), general_admin_expense=Decimal('50'),
        unallocated_overhead=Decimal('20'),
    )
    assert p.gross_profit == Decimal('400.00')
    assert p.operating_income == Decimal('230.00')


def test_variance_total_recomputes(acme, production_order, cost_version):
    v = C.CostVariance.objects.create(
        tenant=acme, production_order=production_order, version=cost_version,
        material_price_variance=Decimal('10'),
        material_usage_variance=Decimal('5'),
        labor_rate_variance=Decimal('-3'),
        labor_efficiency_variance=Decimal('2'),
        overhead_spending_variance=Decimal('1'),
        overhead_volume_variance=Decimal('-2'),
    )
    assert v.total_variance == Decimal('13.00')


# ---------- Workflow helpers ----------

def test_version_workflow_helpers(acme):
    v = C.StandardCostVersion.objects.create(
        tenant=acme, name='V', effective_from=date(2026, 1, 1), status='draft',
    )
    assert v.is_editable() and v.is_approvable()
    v.status = 'approved'
    assert v.is_activatable() and not v.is_editable()
    v.status = 'active'
    assert v.is_archivable()


def test_period_workflow_helpers(acp_open, acp_locked, acp_closed):
    assert acp_open.is_open() and acp_open.is_lockable()
    assert acp_locked.is_closable()
    assert not acp_closed.is_open()


def test_job_close_helper(job):
    assert job.is_closable()


# ---------- Unique constraints ----------

def test_acp_unique_per_tenant_dates(acme, acp_open):
    with pytest.raises(Exception):
        C.AccountingPeriod.objects.create(
            tenant=acme, name='Dup',
            start_date=acp_open.start_date, end_date=acp_open.end_date,
        )


def test_standard_cost_unique_version_product(cost_version, product, standard_cost):
    with pytest.raises(Exception):
        C.StandardCost.objects.create(
            tenant=cost_version.tenant, version=cost_version, product=product,
        )


# ---------- str() smoke ----------

def test_str_methods(acme, acp_open, pool, driver, cost_version, product, standard_cost, production_order, job):
    assert str(acp_open).startswith('ACP-')
    assert pool.code in str(pool)
    assert standard_cost.product.sku in str(standard_cost)
    assert job.job_number.startswith('JC-')
