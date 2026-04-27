"""Shared fixtures for the PPS test suite.

Real fixture shapes per the project conventions established by the PLM /
BOM test suites. Tenant thread-local is reset between tests so the global
manager does not bleed across cases.
"""
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant, set_current_tenant
from apps.plm.models import Product
from apps.pps.models import (
    CapacityCalendar, MasterProductionSchedule, ProductionOrder,
    Routing, RoutingOperation, WorkCenter,
)


@pytest.fixture(autouse=True)
def _clear_tenant():
    """Reset thread-local tenant between tests (defensive)."""
    yield
    set_current_tenant(None)


@pytest.fixture
def acme(db):
    return Tenant.objects.create(name='Acme Test', slug='acme-test', is_active=True)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex Test', slug='globex-test', is_active=True)


@pytest.fixture
def acme_admin(db, acme):
    return User.objects.create_user(
        username='admin_acme_test', password='pw', tenant=acme, is_tenant_admin=True,
    )


@pytest.fixture
def acme_staff(db, acme):
    return User.objects.create_user(
        username='staff_acme_test', password='pw', tenant=acme, is_tenant_admin=False,
    )


@pytest.fixture
def globex_admin(db, globex):
    return User.objects.create_user(
        username='admin_globex_test', password='pw', tenant=globex, is_tenant_admin=True,
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


@pytest.fixture
def product(db, acme):
    return Product.objects.create(
        tenant=acme, sku='SKU-T1', name='Test product', product_type='finished_good',
        unit_of_measure='ea', status='active',
    )


@pytest.fixture
def work_center(db, acme):
    wc = WorkCenter.objects.create(
        tenant=acme, code='WC-T1', name='Test WC', work_center_type='machine',
        capacity_per_hour=Decimal('5'), efficiency_pct=Decimal('100'),
        cost_per_hour=Decimal('50'), is_active=True,
    )
    for dow in range(5):
        CapacityCalendar.objects.create(
            tenant=acme, work_center=wc, day_of_week=dow,
            shift_start=time(8, 0), shift_end=time(17, 0), is_working=True,
        )
    return wc


@pytest.fixture
def routing(db, acme, product, work_center, acme_admin):
    r = Routing.objects.create(
        tenant=acme, product=product, version='A',
        routing_number='ROUT-T1', status='active', is_default=True,
        created_by=acme_admin,
    )
    RoutingOperation.objects.create(
        tenant=acme, routing=r, sequence=10, operation_name='Cut',
        work_center=work_center,
        setup_minutes=Decimal('15'), run_minutes_per_unit=Decimal('5'),
        queue_minutes=Decimal('5'), move_minutes=Decimal('3'),
    )
    RoutingOperation.objects.create(
        tenant=acme, routing=r, sequence=20, operation_name='Assemble',
        work_center=work_center,
        setup_minutes=Decimal('10'), run_minutes_per_unit=Decimal('8'),
        queue_minutes=Decimal('5'), move_minutes=Decimal('3'),
    )
    return r


@pytest.fixture
def draft_mps(db, acme, acme_admin):
    return MasterProductionSchedule.objects.create(
        tenant=acme, mps_number='MPS-T1', name='Test MPS',
        horizon_start=date.today(), horizon_end=date.today() + timedelta(days=28),
        time_bucket='week', status='draft', created_by=acme_admin,
    )


@pytest.fixture
def planned_order(db, acme, product, routing, draft_mps, acme_admin):
    return ProductionOrder.objects.create(
        tenant=acme, order_number='PO-T1', product=product, routing=routing,
        quantity=Decimal('10'), status='planned', priority='normal',
        scheduling_method='forward',
        requested_start=timezone.now(),
        requested_end=timezone.now() + timedelta(days=2),
        created_by=acme_admin,
    )
