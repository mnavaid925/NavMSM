"""Shared fixtures for the Procurement test suite."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant, set_current_tenant
from apps.plm.models import Product

from apps.procurement import models as procm


@pytest.fixture(autouse=True)
def _clear_tenant():
    yield
    set_current_tenant(None)


# ---------- Tenants & users ----------

@pytest.fixture
def acme(db):
    return Tenant.objects.create(name='Acme Test', slug='acme-proc-test', is_active=True)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex Test', slug='globex-proc-test', is_active=True)


@pytest.fixture
def acme_admin(db, acme):
    return User.objects.create_user(
        username='admin_acme_proc', password='pw', tenant=acme,
        is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def acme_staff(db, acme):
    return User.objects.create_user(
        username='staff_acme_proc', password='pw', tenant=acme,
        is_tenant_admin=False, role='operator',
    )


@pytest.fixture
def globex_admin(db, globex):
    return User.objects.create_user(
        username='admin_globex_proc', password='pw', tenant=globex,
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


# ---------- Procurement fixtures ----------

@pytest.fixture
def supplier(db, acme):
    return procm.Supplier.objects.create(
        tenant=acme, code='SUP1', name='Acme Supplier 1',
        email='s1@example.com', currency='USD', is_active=True, is_approved=True,
    )


@pytest.fixture
def supplier2(db, acme):
    return procm.Supplier.objects.create(
        tenant=acme, code='SUP2', name='Acme Supplier 2',
        email='s2@example.com', currency='USD', is_active=True, is_approved=True,
    )


@pytest.fixture
def globex_supplier(db, globex):
    return procm.Supplier.objects.create(
        tenant=globex, code='GBXSUP', name='Globex Supplier',
        currency='USD', is_active=True, is_approved=True,
    )


@pytest.fixture
def supplier_user(db, acme, supplier):
    return User.objects.create_user(
        username='portal_acme_user', password='pw', tenant=acme,
        is_tenant_admin=False, role='supplier', supplier_company=supplier,
    )


@pytest.fixture
def supplier_user_client(client, supplier_user):
    client.force_login(supplier_user)
    return client


@pytest.fixture
def cmp_product(db, acme):
    return Product.objects.create(
        tenant=acme, sku='CMP-PROC', name='Procurement Component',
        product_type='component', unit_of_measure='ea', status='active',
    )


@pytest.fixture
def cmp_product2(db, acme):
    return Product.objects.create(
        tenant=acme, sku='CMP-PROC-2', name='Procurement Component 2',
        product_type='component', unit_of_measure='ea', status='active',
    )


@pytest.fixture
def po(db, acme, supplier, cmp_product, acme_admin):
    today = timezone.now().date()
    po = procm.PurchaseOrder.objects.create(
        tenant=acme, supplier=supplier,
        order_date=today, required_date=today + timedelta(days=14),
        currency='USD', priority='normal', status='draft',
        created_by=acme_admin,
    )
    procm.PurchaseOrderLine.objects.create(
        tenant=acme, po=po, product=cmp_product, description='line 1',
        quantity=Decimal('10'), unit_of_measure='EA', unit_price=Decimal('5.00'),
    )
    po.refresh_from_db()
    po.recompute_totals()
    return po
