"""Shared fixtures for the MRP test suite.

Mirrors the PPS / BOM conftest pattern: fresh tenants per test, autouse reset
of the thread-local tenant, real fixture shapes that match the project's
TenantAwareModel + User contracts.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.bom.models import BillOfMaterials, BOMLine
from apps.core.models import Tenant, set_current_tenant
from apps.plm.models import Product
from apps.mrp.models import (
    ForecastModel, ForecastResult, ForecastRun, InventorySnapshot,
    MRPCalculation, MRPPurchaseRequisition,
    SeasonalityProfile,
)


@pytest.fixture(autouse=True)
def _clear_tenant():
    """Reset thread-local tenant between tests so the global manager does not
    bleed across cases."""
    yield
    set_current_tenant(None)


# ---------------- Tenants + users ----------------

@pytest.fixture
def acme(db):
    return Tenant.objects.create(name='Acme Test', slug='acme-mrp', is_active=True)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex Test', slug='globex-mrp', is_active=True)


@pytest.fixture
def acme_admin(db, acme):
    return User.objects.create_user(
        username='admin_acme_mrp', password='pw',
        tenant=acme, is_tenant_admin=True,
    )


@pytest.fixture
def acme_staff(db, acme):
    return User.objects.create_user(
        username='staff_acme_mrp', password='pw',
        tenant=acme, is_tenant_admin=False,
    )


@pytest.fixture
def globex_admin(db, globex):
    return User.objects.create_user(
        username='admin_globex_mrp', password='pw',
        tenant=globex, is_tenant_admin=True,
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


# ---------------- Products ----------------

@pytest.fixture
def fg_product(db, acme):
    return Product.objects.create(
        tenant=acme, sku='FG-1', name='FG One',
        product_type='finished_good', unit_of_measure='ea', status='active',
    )


@pytest.fixture
def raw_product(db, acme):
    return Product.objects.create(
        tenant=acme, sku='RM-1', name='RM One',
        product_type='raw_material', unit_of_measure='ea', status='active',
    )


# ---------------- BOM ----------------

@pytest.fixture
def released_bom(db, acme, fg_product, raw_product, acme_admin):
    bom = BillOfMaterials.objects.create(
        tenant=acme, product=fg_product, version='A', revision='01',
        bom_number='BOM-T1', bom_type='mbom',
        status='released', is_default=True, created_by=acme_admin,
    )
    BOMLine.objects.create(
        tenant=acme, bom=bom, sequence=10,
        component=raw_product, quantity=Decimal('2'),
        unit_of_measure='ea',
    )
    return bom


# ---------------- Inventory + receipts ----------------

@pytest.fixture
def snapshot_fg(db, acme, fg_product):
    return InventorySnapshot.objects.create(
        tenant=acme, product=fg_product,
        on_hand_qty=Decimal('5'), safety_stock=Decimal('10'),
        reorder_point=Decimal('15'), lead_time_days=14,
        lot_size_method='l4l', lot_size_value=Decimal('0'),
        lot_size_max=Decimal('0'), as_of_date=date.today(),
    )


@pytest.fixture
def snapshot_rm(db, acme, raw_product):
    return InventorySnapshot.objects.create(
        tenant=acme, product=raw_product,
        on_hand_qty=Decimal('30'), safety_stock=Decimal('20'),
        reorder_point=Decimal('40'), lead_time_days=7,
        lot_size_method='foq', lot_size_value=Decimal('50'),
        lot_size_max=Decimal('0'), as_of_date=date.today(),
    )


# ---------------- Forecast model + run ----------------

@pytest.fixture
def forecast_model(db, acme, acme_admin):
    return ForecastModel.objects.create(
        tenant=acme, name='SMA-3', method='moving_avg',
        params={'window': 3}, period_type='week',
        horizon_periods=4, is_active=True, created_by=acme_admin,
    )


@pytest.fixture
def completed_forecast_run(db, acme, forecast_model, fg_product):
    run = ForecastRun.objects.create(
        tenant=acme, run_number='FRUN-00001',
        forecast_model=forecast_model, run_date=date.today(),
        status='completed',
    )
    today = date.today()
    for w in range(4):
        ps = today + timedelta(days=w * 7)
        ForecastResult.objects.create(
            tenant=acme, run=run, product=fg_product,
            period_start=ps, period_end=ps + timedelta(days=6),
            forecasted_qty=Decimal('80'),
            lower_bound=Decimal('68'), upper_bound=Decimal('92'),
            confidence_pct=Decimal('80'),
        )
    return run


# ---------------- MRP calculation ----------------

@pytest.fixture
def calc(db, acme, acme_admin):
    today = date.today()
    return MRPCalculation.objects.create(
        tenant=acme, mrp_number='MRP-00001', name='Test calc',
        horizon_start=today, horizon_end=today + timedelta(days=28),
        time_bucket='week', status='draft', started_by=acme_admin,
    )


# ---------------- Convenience PR factory ----------------

@pytest.fixture
def make_pr(db):
    """Return a callable that creates an MRPPurchaseRequisition row."""
    def _make(tenant, calc, product, *, status='draft', pr_number='MPR-T1', priority='normal'):
        return MRPPurchaseRequisition.objects.create(
            tenant=tenant, pr_number=pr_number, mrp_calculation=calc,
            product=product, quantity=Decimal('10'),
            required_by_date=date.today() + timedelta(days=14),
            suggested_release_date=date.today() + timedelta(days=7),
            status=status, priority=priority,
        )
    return _make
