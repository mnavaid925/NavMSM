"""Shared fixtures for the Labor & Workforce test suite."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant, set_current_tenant
from apps.labor import models as L


@pytest.fixture(autouse=True)
def _clear_tenant():
    yield
    set_current_tenant(None)


# ---------- Tenants & users ----------

@pytest.fixture
def acme(db):
    return Tenant.objects.create(name='Acme Labor', slug='acme-labor-test', is_active=True)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex Labor', slug='globex-labor-test', is_active=True)


@pytest.fixture
def acme_admin(db, acme):
    return User.objects.create_user(
        username='admin_acme_labor', password='pw', tenant=acme,
        is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def acme_staff(db, acme):
    return User.objects.create_user(
        username='staff_acme_labor', password='pw', tenant=acme,
        is_tenant_admin=False, role='operator',
    )


@pytest.fixture
def globex_admin(db, globex):
    return User.objects.create_user(
        username='admin_globex_labor', password='pw', tenant=globex,
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


# ---------- Labor fixtures ----------

@pytest.fixture
def department(db, acme):
    return L.Department.objects.create(tenant=acme, code='PROD', name='Production')


@pytest.fixture
def position(db, acme, department):
    return L.Position.objects.create(
        tenant=acme, code='OP-JR', title='Junior Operator',
        department=department, level='junior',
    )


@pytest.fixture
def employee(db, acme, department, position):
    return L.Employee.objects.create(
        tenant=acme, first_name='Alex', last_name='Adams',
        email='alex@example.com', department=department, position=position,
        employment_type='permanent', hire_date=date.today() - timedelta(days=365),
        status='active',
    )


@pytest.fixture
def employee2(db, acme, department, position):
    return L.Employee.objects.create(
        tenant=acme, first_name='Brian', last_name='Brown',
        department=department, position=position,
        hire_date=date.today() - timedelta(days=180),
        status='active',
    )


@pytest.fixture
def globex_employee(db, globex):
    dept = L.Department.objects.create(tenant=globex, code='PROD', name='Production')
    pos = L.Position.objects.create(
        tenant=globex, code='OP', title='Operator', department=dept, level='mid',
    )
    return L.Employee.objects.create(
        tenant=globex, first_name='G', last_name='X',
        department=dept, position=pos,
        hire_date=date.today() - timedelta(days=10),
    )


@pytest.fixture
def skill(db, acme):
    return L.Skill.objects.create(
        tenant=acme, code='CNC-LATHE', name='CNC Lathe', category='operations',
    )


@pytest.fixture
def certification(db, acme):
    return L.Certification.objects.create(
        tenant=acme, code='FORK', name='Forklift License',
        issuing_authority='OSHA', valid_period_days=365,
    )


@pytest.fixture
def shift(db, acme):
    return L.Shift.objects.create(
        tenant=acme, code='MORN', name='Morning',
        start_time=time(6, 0), end_time=time(14, 0), break_minutes=30,
    )


@pytest.fixture
def leave_type(db, acme):
    return L.LeaveType.objects.create(
        tenant=acme, code='ANN', name='Annual Leave', paid=True,
        default_annual_quota_days=Decimal('20'),
    )


@pytest.fixture
def cost_center(db, acme):
    return L.CostCenter.objects.create(
        tenant=acme, code='CC-PROD', name='Production', cc_type='production',
    )


@pytest.fixture
def labor_rate(db, acme, employee):
    return L.LaborRate.objects.create(
        tenant=acme, employee=employee, hourly_rate=Decimal('25.00'),
        overtime_multiplier=Decimal('1.50'),
        effective_from=date.today() - timedelta(days=180),
    )


@pytest.fixture
def training_program(db, acme):
    return L.TrainingProgram.objects.create(
        tenant=acme, code='TP-1', name='Safety Refresher',
        delivery_mode='classroom', duration_hours=Decimal('4.0'),
    )


@pytest.fixture
def incentive_scheme(db, acme):
    return L.IncentiveScheme.objects.create(
        tenant=acme, code='PR-1', name='Piece Rate Std', scheme_type='piece_rate',
        effective_from=date.today() - timedelta(days=30), is_active=True,
    )


@pytest.fixture
def incentive_period(db, acme):
    today = date.today()
    return L.IncentivePeriod.objects.create(
        tenant=acme, name='Test Period',
        start_date=today.replace(day=1),
        end_date=today,
        status='open',
    )
