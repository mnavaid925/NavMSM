"""Full CRUD smoke + workflow happy paths."""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse


pytestmark = pytest.mark.django_db


# ---------- List smoke ----------

LIST_URLS = [
    'cost:index', 'cost:version_list', 'cost:standard_cost_list',
    'cost:actual_cost_list', 'cost:variance_list', 'cost:job_list',
    'cost:wip_list', 'cost:driver_list', 'cost:pool_list', 'cost:rate_list',
    'cost:driver_actuals_list', 'cost:allocation_list',
    'cost:period_list', 'cost:cogm_list', 'cost:margin_list', 'cost:pnl_list',
    'cost:version_compare',
]


@pytest.mark.parametrize('name', LIST_URLS)
def test_list_pages_render(admin_client, name):
    r = admin_client.get(reverse(name))
    assert r.status_code == 200


# ---------- Create flows ----------

def test_create_cost_driver(admin_client, acme):
    r = admin_client.post(reverse('cost:driver_create'), data={
        'name': 'Energy', 'code': 'ENERGY', 'unit_of_measure': 'kwh',
        'is_active': 'on',
    })
    assert r.status_code == 302
    from apps.cost import models as C
    assert C.CostDriver.objects.filter(tenant=acme, code='ENERGY').exists()


def test_create_period(admin_client, acme):
    r = admin_client.post(reverse('cost:period_create'), data={
        'name': 'Apr 2026', 'period_type': 'monthly',
        'start_date': '2026-04-01', 'end_date': '2026-04-30',
    })
    assert r.status_code == 302
    from apps.cost import models as C
    assert C.AccountingPeriod.objects.filter(tenant=acme, name='Apr 2026').exists()


def test_create_cost_version(admin_client, acme):
    r = admin_client.post(reverse('cost:version_create'), data={
        'name': 'Q2 2026', 'effective_from': '2026-04-01',
    })
    assert r.status_code == 302


def test_create_pool_and_rate(admin_client, acme, driver, acp_open):
    r = admin_client.post(reverse('cost:pool_create'), data={
        'name': 'Energy Costs', 'code': 'ENRG', 'pool_type': 'variable',
        'default_driver': driver.pk, 'allocation_method': 'volume',
        'is_active': 'on',
    })
    assert r.status_code == 302
    from apps.cost import models as C
    pool = C.OverheadPool.objects.get(tenant=acme, code='ENRG')
    r2 = admin_client.post(reverse('cost:rate_create'), data={
        'pool': pool.pk, 'period': acp_open.pk, 'driver': driver.pk,
        'budgeted_amount': '5000', 'budgeted_driver_qty': '500',
        'is_active': 'on',
    })
    assert r2.status_code == 302
    rate = C.OverheadRate.objects.get(pool=pool, period=acp_open)
    assert rate.rate_per_driver_unit == Decimal('10.000000')


# ---------- Standard Cost workflow ----------

def test_version_approve_workflow(admin_client, acme):
    from apps.cost import models as C
    v = C.StandardCostVersion.objects.create(
        tenant=acme, name='V', effective_from=date(2026, 1, 1), status='draft',
    )
    r = admin_client.post(reverse('cost:version_approve', args=[v.pk]),
                          data={'notes': 'Looks good'})
    assert r.status_code == 302
    v.refresh_from_db()
    assert v.status == 'approved'
    assert v.approved_by is not None


def test_version_approve_blocked_without_notes(admin_client, acme):
    from apps.cost import models as C
    v = C.StandardCostVersion.objects.create(
        tenant=acme, name='V', effective_from=date(2026, 1, 1), status='draft',
    )
    r = admin_client.post(reverse('cost:version_approve', args=[v.pk]), data={'notes': ''})
    v.refresh_from_db()
    assert v.status == 'draft'  # Blocked


def test_version_activate_archives_prior_active(admin_client, acme):
    from apps.cost import models as C
    old = C.StandardCostVersion.objects.create(
        tenant=acme, name='Old', effective_from=date(2025, 1, 1), status='active',
    )
    new = C.StandardCostVersion.objects.create(
        tenant=acme, name='New', effective_from=date(2026, 1, 1), status='approved',
    )
    r = admin_client.post(reverse('cost:version_activate', args=[new.pk]))
    assert r.status_code == 302
    old.refresh_from_db()
    new.refresh_from_db()
    assert old.status == 'archived'
    assert new.status == 'active'


# ---------- Period lock + close ----------

def test_period_lock(admin_client, acp_open):
    r = admin_client.post(reverse('cost:period_lock', args=[acp_open.pk]),
                          data={'confirm': 'on', 'notes': ''})
    assert r.status_code == 302
    acp_open.refresh_from_db()
    assert acp_open.status == 'locked'


def test_period_close_only_from_locked(admin_client, acp_locked):
    r = admin_client.post(reverse('cost:period_close', args=[acp_locked.pk]))
    assert r.status_code == 302
    acp_locked.refresh_from_db()
    assert acp_locked.status == 'closed'


# ---------- Job + WIP entry ----------

def test_create_wip_entry_via_view(admin_client, acme, job):
    r = admin_client.post(reverse('cost:wip_create'), data={
        'job': job.pk, 'entry_type': 'material_issued',
        'amount': '100.00', 'quantity': '5', 'unit_of_measure': 'ea',
    })
    assert r.status_code == 302
    job.refresh_from_db()
    assert job.total_material == Decimal('100.00')


def test_close_job_with_zero_balance(admin_client, acme, job):
    # Build to zero
    from apps.cost.services import wip as wip_svc
    wip_svc.post_wip_entry(tenant=acme, job=job, entry_type='material_issued', amount=Decimal('100'))
    wip_svc.post_wip_entry(tenant=acme, job=job, entry_type='completion', amount=Decimal('100'))
    r = admin_client.post(reverse('cost:job_close', args=[job.pk]))
    assert r.status_code == 302
    job.refresh_from_db()
    assert job.status == 'closed'


# ---------- Recompute version ----------

def test_recompute_version(admin_client, cost_version):
    r = admin_client.post(reverse('cost:version_recompute', args=[cost_version.pk]))
    # Could redirect or render — both fine; should not 500.
    assert r.status_code in (200, 302)


# ---------- Compare ----------

def test_compare_view_renders_with_versions(admin_client, acme):
    from apps.cost import models as C
    v1 = C.StandardCostVersion.objects.create(
        tenant=acme, name='V1', effective_from=date(2025, 1, 1),
    )
    v2 = C.StandardCostVersion.objects.create(
        tenant=acme, name='V2', effective_from=date(2026, 1, 1),
    )
    r = admin_client.get(reverse('cost:version_compare') + f'?v1={v1.pk}&v2={v2.pk}')
    assert r.status_code == 200


# ---------- Generate reports ----------

def test_cogm_generate_view(admin_client, acp_closed):
    r = admin_client.post(reverse('cost:cogm_generate', args=[acp_closed.pk]))
    assert r.status_code == 302
    from apps.cost import models as C
    assert C.COGMReport.objects.filter(period=acp_closed).exists()


def test_pnl_generate_view(admin_client, acp_closed):
    r = admin_client.post(reverse('cost:pnl_generate'), data={
        'period': acp_closed.pk,
        'selling_expense': '100', 'general_admin_expense': '50',
        'unallocated_overhead': '10',
    })
    assert r.status_code == 302
    from apps.cost import models as C
    assert C.PlantPnLReport.objects.filter(period=acp_closed).exists()
