"""Shared fixtures for the MES test suite.

Real fixture shapes per the project conventions established by the PLM /
BOM / PPS test suites. Tenant thread-local is reset between tests so the
global manager does not bleed across cases.
"""
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant, set_current_tenant
from apps.plm.models import Product
from apps.pps.models import (
    CapacityCalendar, Routing, RoutingOperation, ProductionOrder, WorkCenter,
)

from apps.mes.models import (
    AndonAlert, MESWorkOrder, MESWorkOrderOperation, OperatorTimeLog,
    ProductionReport, ShopFloorOperator, WorkInstruction,
    WorkInstructionVersion,
)
from apps.mes.services import dispatcher


@pytest.fixture(autouse=True)
def _clear_tenant():
    """Reset thread-local tenant between tests (defensive)."""
    yield
    set_current_tenant(None)


# ---------- Tenants & users ----------

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


# ---------- PLM / PPS prerequisites ----------

@pytest.fixture
def product(db, acme):
    return Product.objects.create(
        tenant=acme, sku='SKU-MES1', name='Test product', product_type='finished_good',
        unit_of_measure='ea', status='active',
    )


@pytest.fixture
def globex_product(db, globex):
    return Product.objects.create(
        tenant=globex, sku='SKU-MES-GBX', name='Globex product',
        product_type='finished_good', unit_of_measure='ea', status='active',
    )


@pytest.fixture
def work_center(db, acme):
    wc = WorkCenter.objects.create(
        tenant=acme, code='WC-MES1', name='Test WC', work_center_type='machine',
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
def globex_work_center(db, globex):
    return WorkCenter.objects.create(
        tenant=globex, code='WC-GBX', name='Globex WC', work_center_type='machine',
        capacity_per_hour=Decimal('5'), efficiency_pct=Decimal('100'),
        cost_per_hour=Decimal('50'), is_active=True,
    )


@pytest.fixture
def routing(db, acme, product, work_center, acme_admin):
    r = Routing.objects.create(
        tenant=acme, product=product, version='A',
        routing_number='ROUT-MES1', status='active', is_default=True,
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
def released_po(db, acme, product, routing, acme_admin):
    return ProductionOrder.objects.create(
        tenant=acme, order_number='PO-MES1', product=product, routing=routing,
        quantity=Decimal('10'), status='released', priority='normal',
        scheduling_method='forward',
        requested_start=timezone.now(),
        requested_end=timezone.now() + timedelta(days=2),
        created_by=acme_admin,
    )


@pytest.fixture
def planned_po(db, acme, product, routing, acme_admin):
    return ProductionOrder.objects.create(
        tenant=acme, order_number='PO-MES2', product=product, routing=routing,
        quantity=Decimal('5'), status='planned', priority='normal',
        scheduling_method='forward', created_by=acme_admin,
    )


# ---------- MES seed pieces ----------

@pytest.fixture
def operator(db, acme, acme_staff, work_center):
    return ShopFloorOperator.objects.create(
        tenant=acme, user=acme_staff, badge_number='B0001',
        default_work_center=work_center, is_active=True,
    )


@pytest.fixture
def globex_operator(db, globex, globex_admin, globex_work_center):
    return ShopFloorOperator.objects.create(
        tenant=globex, user=globex_admin, badge_number='B0001-GBX',
        default_work_center=globex_work_center, is_active=True,
    )


@pytest.fixture
def work_order(db, acme, released_po, acme_admin):
    """Real dispatch flow so the MESWorkOrderOperation rows exist."""
    return dispatcher.dispatch_production_order(released_po, dispatched_by=acme_admin)


@pytest.fixture
def first_op(db, work_order):
    return work_order.operations.order_by('sequence').first()


@pytest.fixture
def open_andon(db, acme, work_center, acme_admin):
    return AndonAlert.objects.create(
        tenant=acme, alert_number='AND-T0001',
        alert_type='quality', severity='high',
        title='Test alert', message='Surface defect',
        work_center=work_center,
        status='open', raised_by=acme_admin,
        raised_at=timezone.now(),
    )


@pytest.fixture
def draft_instruction(db, acme, routing, acme_admin):
    rop = routing.operations.order_by('sequence').first()
    return WorkInstruction.objects.create(
        tenant=acme, instruction_number='SOP-T0001',
        title='Test SOP', doc_type='sop',
        routing_operation=rop, status='draft', created_by=acme_admin,
    )


@pytest.fixture
def draft_instruction_version(db, draft_instruction, acme_admin):
    return WorkInstructionVersion.objects.create(
        tenant=draft_instruction.tenant, instruction=draft_instruction,
        version='1.0', content='Step 1: do the thing.',
        status='draft', uploaded_by=acme_admin,
    )
