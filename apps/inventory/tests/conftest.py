"""Shared fixtures for the Inventory test suite."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant, set_current_tenant
from apps.plm.models import Product

from apps.inventory import models as inv_models


@pytest.fixture(autouse=True)
def _clear_tenant():
    yield
    set_current_tenant(None)


# ---------- Tenants & users ----------

@pytest.fixture
def acme(db):
    return Tenant.objects.create(name='Acme Test', slug='acme-inv-test', is_active=True)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex Test', slug='globex-inv-test', is_active=True)


@pytest.fixture
def acme_admin(db, acme):
    return User.objects.create_user(
        username='admin_acme_inv', password='pw', tenant=acme, is_tenant_admin=True,
    )


@pytest.fixture
def acme_staff(db, acme):
    return User.objects.create_user(
        username='staff_acme_inv', password='pw', tenant=acme, is_tenant_admin=False,
    )


@pytest.fixture
def globex_admin(db, globex):
    return User.objects.create_user(
        username='admin_globex_inv', password='pw', tenant=globex, is_tenant_admin=True,
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


# ---------- PLM prerequisites ----------

@pytest.fixture
def fg_product(db, acme):
    return Product.objects.create(
        tenant=acme, sku='FG-INV', name='Finished good',
        product_type='finished_good', unit_of_measure='ea', status='active',
        tracking_mode='lot',
    )


@pytest.fixture
def cmp_product(db, acme):
    return Product.objects.create(
        tenant=acme, sku='CMP-INV', name='Component',
        product_type='component', unit_of_measure='ea', status='active',
    )


@pytest.fixture
def globex_product(db, globex):
    return Product.objects.create(
        tenant=globex, sku='FG-GBX', name='Globex finished',
        product_type='finished_good', unit_of_measure='ea', status='active',
    )


# ---------- Inventory fixtures ----------

@pytest.fixture
def warehouse(db, acme):
    return inv_models.Warehouse.objects.create(
        tenant=acme, code='MAIN', name='Main', is_default=True, is_active=True,
    )


@pytest.fixture
def globex_warehouse(db, globex):
    return inv_models.Warehouse.objects.create(
        tenant=globex, code='GBX', name='Globex DC', is_default=True, is_active=True,
    )


@pytest.fixture
def receiving_zone(db, acme, warehouse):
    return inv_models.WarehouseZone.objects.create(
        tenant=acme, warehouse=warehouse, code='RECV', name='Receiving',
        zone_type='receiving',
    )


@pytest.fixture
def storage_zone(db, acme, warehouse):
    return inv_models.WarehouseZone.objects.create(
        tenant=acme, warehouse=warehouse, code='STOR', name='Storage',
        zone_type='storage',
    )


@pytest.fixture
def bin_a(db, acme, storage_zone):
    return inv_models.StorageBin.objects.create(
        tenant=acme, zone=storage_zone, code='STOR-01', bin_type='shelf',
    )


@pytest.fixture
def bin_b(db, acme, storage_zone):
    return inv_models.StorageBin.objects.create(
        tenant=acme, zone=storage_zone, code='STOR-02', bin_type='shelf',
    )


@pytest.fixture
def bin_recv(db, acme, receiving_zone):
    return inv_models.StorageBin.objects.create(
        tenant=acme, zone=receiving_zone, code='RECV-01', bin_type='shelf',
    )


@pytest.fixture
def lot(db, acme, fg_product):
    today = timezone.now().date()
    return inv_models.Lot.objects.create(
        tenant=acme, product=fg_product, lot_number='LOT-001',
        manufactured_date=today - timedelta(days=10),
        expiry_date=today + timedelta(days=355),
        status='active',
    )
