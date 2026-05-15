"""Pytest fixtures for Module 18 - Returns & RMA tests."""
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.core.models import Tenant, set_current_tenant


@pytest.fixture
def tenant_a(db):
    t = Tenant.objects.create(name='Tenant A', slug='tenant-a')
    set_current_tenant(t)
    yield t
    set_current_tenant(None)


@pytest.fixture
def tenant_b(db):
    return Tenant.objects.create(name='Tenant B', slug='tenant-b')


@pytest.fixture
def tenant_admin(db, tenant_a):
    User = get_user_model()
    return User.objects.create_user(
        username='admin_a', password='pw', email='admin@example.com',
        tenant=tenant_a, is_tenant_admin=True,
    )


@pytest.fixture
def staff_user(db, tenant_a):
    User = get_user_model()
    return User.objects.create_user(
        username='staff_a', password='pw', email='staff@example.com',
        tenant=tenant_a, is_tenant_admin=False,
    )


@pytest.fixture
def customer(db, tenant_a):
    from apps.sales.models import Customer
    return Customer.objects.create(
        tenant=tenant_a, name='ACME Returns Test',
        customer_class='standard', currency='USD', payment_terms='net30',
        credit_limit=Decimal('10000'),
    )


@pytest.fixture
def product(db, tenant_a):
    from apps.plm.models import Product
    return Product.objects.create(
        tenant=tenant_a, sku='WIDGET-A', name='Test Widget A',
    )


@pytest.fixture
def supplier(db, tenant_a):
    from apps.procurement.models import Supplier
    return Supplier.objects.create(
        tenant=tenant_a, code='SUP-A', name='Test Supplier A',
    )


@pytest.fixture
def warehouse_with_bin(db, tenant_a):
    from apps.inventory.models import StorageBin, Warehouse, WarehouseZone
    wh = Warehouse.objects.create(
        tenant=tenant_a, code='WH-A', name='Test Warehouse A',
    )
    zone = WarehouseZone.objects.create(
        tenant=tenant_a, warehouse=wh, code='Z1', name='Receiving',
        zone_type='receiving',
    )
    bin_ = StorageBin.objects.create(
        tenant=tenant_a, zone=zone, code='B1', bin_type='floor',
    )
    return wh, bin_


@pytest.fixture
def employee(db, tenant_a):
    from apps.labor.models import Department, Employee, Position
    dept = Department.objects.create(tenant=tenant_a, name='Repair', code='RPR')
    pos = Position.objects.create(tenant=tenant_a, title='Tech', code='TECH', department=dept)
    return Employee.objects.create(
        tenant=tenant_a, employee_number='EMP-001',
        first_name='Test', last_name='Tech',
        department=dept, position=pos,
        employment_type='full_time', hire_date=date(2020, 1, 1),
        status='active',
    )


@pytest.fixture
def reason(db, tenant_a):
    from apps.rma.models import RMAReason
    return RMAReason.objects.create(
        tenant=tenant_a, name='Test Reason', category='quality_defect',
    )


@pytest.fixture
def policy(db, tenant_a):
    from apps.rma.models import WarrantyPolicy
    return WarrantyPolicy.objects.create(
        tenant=tenant_a, name='Test 12mo Policy',
        coverage_type='parts_and_labor', duration_months=12,
    )


@pytest.fixture
def rma_request(db, tenant_a, customer, product, reason):
    """Draft RMA with one line."""
    from apps.rma.models import RMALine, RMARequest
    rma = RMARequest.objects.create(
        tenant=tenant_a, customer=customer,
        requested_action='refund', status='draft',
        customer_reference='TEST-REF-001',
    )
    RMALine.objects.create(
        tenant=tenant_a, rma=rma, product=product,
        quantity=Decimal('2'), unit_price=Decimal('100'),
        reason=reason, condition_reported='defective',
    )
    return rma
