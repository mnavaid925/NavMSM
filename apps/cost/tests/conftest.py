"""Shared fixtures for the Cost Management & Accounting test suite."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant, set_current_tenant
from apps.cost import models as C


@pytest.fixture(autouse=True)
def _clear_tenant():
    yield
    set_current_tenant(None)


# ---------- Tenants & users ----------

@pytest.fixture
def acme(db):
    return Tenant.objects.create(name='Acme Cost', slug='acme-cost-test', is_active=True)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex Cost', slug='globex-cost-test', is_active=True)


@pytest.fixture
def acme_admin(db, acme):
    return User.objects.create_user(
        username='admin_acme_cost', password='pw', tenant=acme,
        is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def acme_staff(db, acme):
    return User.objects.create_user(
        username='staff_acme_cost', password='pw', tenant=acme,
        is_tenant_admin=False, role='operator',
    )


@pytest.fixture
def globex_admin(db, globex):
    return User.objects.create_user(
        username='admin_globex_cost', password='pw', tenant=globex,
        is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def admin_client(client, acme_admin):
    client.force_login(acme_admin)
    return client


@pytest.fixture
def staff_client(client, acme_staff):
    client.force_login(acme_staff)
    return client


@pytest.fixture
def globex_client(client, globex_admin):
    client.force_login(globex_admin)
    return client


# ---------- Common cost fixtures ----------

@pytest.fixture
def acp_open(db, acme):
    today = date.today()
    return C.AccountingPeriod.objects.create(
        tenant=acme, name='Test Open Period',
        start_date=today.replace(day=1),
        end_date=today.replace(day=28),
        status='open',
    )


@pytest.fixture
def acp_locked(db, acme):
    return C.AccountingPeriod.objects.create(
        tenant=acme, name='Test Locked Period',
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
        status='locked',
    )


@pytest.fixture
def acp_closed(db, acme):
    return C.AccountingPeriod.objects.create(
        tenant=acme, name='Test Closed Period',
        start_date=date(2025, 12, 1), end_date=date(2025, 12, 31),
        status='closed',
    )


@pytest.fixture
def driver(db, acme):
    return C.CostDriver.objects.create(tenant=acme, code='MH', name='Machine Hours')


@pytest.fixture
def pool(db, acme, driver):
    return C.OverheadPool.objects.create(
        tenant=acme, code='RENT', name='Factory Rent',
        pool_type='fixed', default_driver=driver, allocation_method='abc',
    )


@pytest.fixture
def overhead_rate(db, acme, pool, acp_open, driver):
    return C.OverheadRate.objects.create(
        tenant=acme, pool=pool, period=acp_open, driver=driver,
        budgeted_amount=Decimal('1000'), budgeted_driver_qty=Decimal('100'),
    )


@pytest.fixture
def cost_version(db, acme):
    return C.StandardCostVersion.objects.create(
        tenant=acme, name='Test Version', effective_from=date(2026, 1, 1),
        status='active',
    )


@pytest.fixture
def product(db, acme):
    from apps.plm.models import Product, ProductCategory
    cat = ProductCategory.objects.create(tenant=acme, code='C1', name='Test Cat')
    return Product.objects.create(
        tenant=acme, sku='SKU-T1', name='Test Product',
        category=cat, product_type='finished_good', unit_of_measure='ea',
        standard_sale_price=Decimal('200'),
    )


@pytest.fixture
def standard_cost(db, acme, cost_version, product):
    return C.StandardCost.objects.create(
        tenant=acme, version=cost_version, product=product,
        material_cost=Decimal('20'), labor_cost=Decimal('15'),
        overhead_cost=Decimal('10'), tooling_cost=Decimal('1'),
        source='manual',
    )


@pytest.fixture
def production_order(db, acme, product):
    from apps.pps.models import ProductionOrder
    po = ProductionOrder(
        tenant=acme, product=product, order_number='PO-T1',
        quantity=Decimal('10'), status='released',
    )
    po.save()
    return po


@pytest.fixture
def job(db, acme, production_order):
    return C.JobCost.objects.create(
        tenant=acme, production_order=production_order, status='open',
    )
