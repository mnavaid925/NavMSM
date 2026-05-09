"""Shared fixtures for the Energy & Utility Management test suite."""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant, set_current_tenant
from apps.utility import models as U


@pytest.fixture(autouse=True)
def _clear_tenant():
    yield
    set_current_tenant(None)


# ---------- Tenants & users ----------

@pytest.fixture
def acme(db):
    return Tenant.objects.create(name='Acme Util', slug='acme-util-test', is_active=True)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex Util', slug='globex-util-test', is_active=True)


@pytest.fixture
def acme_admin(db, acme):
    return User.objects.create_user(
        username='admin_acme_util', password='pw', tenant=acme,
        is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def acme_staff(db, acme):
    return User.objects.create_user(
        username='staff_acme_util', password='pw', tenant=acme,
        is_tenant_admin=False, role='operator',
    )


@pytest.fixture
def globex_admin(db, globex):
    return User.objects.create_user(
        username='admin_globex_util', password='pw', tenant=globex,
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


# ---------- Cost dependencies (period needed for many utility models) ----------

@pytest.fixture
def acp_open(db, acme):
    from apps.cost.models import AccountingPeriod
    today = date.today()
    return AccountingPeriod.objects.create(
        tenant=acme, name='Util Test Period',
        start_date=today.replace(day=1),
        end_date=today.replace(day=28),
        status='open',
    )


@pytest.fixture
def cost_driver_kwh(db, acme):
    from apps.cost.models import CostDriver
    return CostDriver.objects.create(tenant=acme, code='KWH', name='kWh', unit_of_measure='kwh')


# ---------- Utility fixtures ----------

@pytest.fixture
def utility_type_electricity(db, acme, cost_driver_kwh):
    return U.UtilityType.objects.create(
        tenant=acme, code='electricity', name='Electricity',
        unit_of_measure='kwh', cost_driver=cost_driver_kwh,
    )


@pytest.fixture
def utility_type_water(db, acme):
    return U.UtilityType.objects.create(
        tenant=acme, code='water', name='Water', unit_of_measure='m3',
    )


@pytest.fixture
def meter(db, acme, utility_type_electricity):
    return U.UtilityMeter.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        name='Main Electricity', is_active=True,
    )


@pytest.fixture
def water_meter(db, acme, utility_type_water):
    return U.UtilityMeter.objects.create(
        tenant=acme, utility_type=utility_type_water,
        name='Main Water', is_active=True,
    )


@pytest.fixture
def tariff(db, acme, utility_type_electricity):
    return U.UtilityTariff.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        name='Standard Electricity', effective_from=date.today(),
        flat_rate=Decimal('0.12'), currency='USD',
    )


@pytest.fixture
def emission_factor_grid(db, acme):
    return U.EmissionFactor.objects.create(
        tenant=acme, source_type='electricity_grid', scope='scope_2',
        factor=Decimal('0.42'), unit_of_measure='kwh',
        effective_from=date(2024, 1, 1), is_active=True,
    )


@pytest.fixture
def consumption(db, acme, meter):
    now = timezone.now()
    return U.UtilityConsumption.objects.create(
        tenant=acme, meter=meter,
        period_start=now - timedelta(hours=1), period_end=now,
        start_reading=Decimal('100'), end_reading=Decimal('150'),
        unit_cost=Decimal('0.12'),
        source='manual',
    )
