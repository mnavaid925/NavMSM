"""Shared fixtures for the EAM test suite."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant, set_current_tenant
from apps.plm.models import Product

from apps.eam import models as eam_m


@pytest.fixture(autouse=True)
def _clear_tenant():
    yield
    set_current_tenant(None)


# ---------- Tenants & users ----------

@pytest.fixture
def acme(db):
    return Tenant.objects.create(name='Acme EAM', slug='acme-eam-test', is_active=True)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex EAM', slug='globex-eam-test', is_active=True)


@pytest.fixture
def acme_admin(db, acme):
    return User.objects.create_user(
        username='admin_acme_eam', password='pw', tenant=acme,
        is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def acme_staff(db, acme):
    return User.objects.create_user(
        username='staff_acme_eam', password='pw', tenant=acme,
        is_tenant_admin=False, role='operator',
    )


@pytest.fixture
def globex_admin(db, globex):
    return User.objects.create_user(
        username='admin_globex_eam', password='pw', tenant=globex,
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


# ---------- EAM fixtures ----------

@pytest.fixture
def category(db, acme):
    return eam_m.AssetCategory.objects.create(
        tenant=acme, name='Pumps', is_active=True,
    )


@pytest.fixture
def asset(db, acme, category):
    return eam_m.Asset.objects.create(
        tenant=acme, name='Process Pump', category=category,
        manufacturer='Acme', model_number='P-100', serial_number='SN1',
        criticality='high', status='operational', is_active=True,
    )


@pytest.fixture
def globex_asset(db, globex):
    return eam_m.Asset.objects.create(
        tenant=globex, name='Globex Pump',
        criticality='medium', status='operational', is_active=True,
    )


@pytest.fixture
def cmp_product(db, acme):
    return Product.objects.create(
        tenant=acme, sku='SPARE-1', name='Bearing',
        product_type='component', unit_of_measure='ea', status='active',
    )


@pytest.fixture
def pm_plan(db, acme, asset):
    return eam_m.MaintenancePlan.objects.create(
        tenant=acme, asset=asset, name='Quarterly Lube',
        trigger_type='calendar', frequency_days=90,
        next_due_at=date.today() + timedelta(days=30),
        is_active=True,
    )


@pytest.fixture
def pm_schedule(db, acme, pm_plan):
    return eam_m.PMSchedule.objects.create(
        tenant=acme, plan=pm_plan,
        scheduled_date=date.today() + timedelta(days=7),
        status='scheduled',
    )


@pytest.fixture
def monitoring_point(db, acme, asset):
    return eam_m.ConditionMonitoringPoint.objects.create(
        tenant=acme, asset=asset, name='Bearing Vibration',
        parameter='vibration', unit='mm/s',
        low_alarm=None, high_alarm=Decimal('5.0'),
        is_active=True,
    )


@pytest.fixture
def mwo(db, acme, asset, acme_admin):
    return eam_m.MaintenanceWorkOrder.objects.create(
        tenant=acme, asset=asset, wo_type='corrective', priority='medium',
        title='Investigate noise', status='draft',
        reported_by=acme_admin, reported_at=timezone.now(),
    )


@pytest.fixture
def tool(db, acme):
    return eam_m.Tool.objects.create(
        tenant=acme, name='Carbide End Mill', tool_type='cutting_tool',
        status='available', expected_life_cycles=10000, is_active=True,
    )


@pytest.fixture
def mold(db, acme):
    return eam_m.Tool.objects.create(
        tenant=acme, name='4-Cavity Cover Mold', tool_type='mold',
        status='available', cavity_count=4, is_active=True,
    )
