"""Pytest fixtures for Module 17 - Sales tests."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.core.models import Tenant, set_current_tenant
from apps.sales.models import (
    CustomerCategory,
    PriceList,
    Customer,
)


@pytest.fixture
def tenant_a(db):
    t = Tenant.objects.create(name='Tenant A', slug='tenant-a')
    set_current_tenant(t)
    yield t
    set_current_tenant(None)


@pytest.fixture
def tenant_b(db):
    t = Tenant.objects.create(name='Tenant B', slug='tenant-b')
    return t


@pytest.fixture
def tenant_admin(db, tenant_a):
    User = get_user_model()
    u = User.objects.create_user(
        username='admin_a', password='pw', email='a@example.com',
        tenant=tenant_a, is_tenant_admin=True,
    )
    return u


@pytest.fixture
def customer(db, tenant_a):
    return Customer.objects.create(
        tenant=tenant_a, name='ACME', customer_class='key',
        currency='USD', payment_terms='net30',
        credit_limit=Decimal('10000'),
    )


@pytest.fixture
def category(db, tenant_a):
    return CustomerCategory.objects.create(
        tenant=tenant_a, name='Manufacturing',
    )


@pytest.fixture
def default_pricelist(db, tenant_a):
    return PriceList.objects.create(
        tenant=tenant_a, name='Standard PL', currency='USD',
        is_default=True, is_active=True,
    )
