"""Shared fixtures for PLM tests."""
import pytest
from django.test import Client

from apps.accounts.models import User, UserProfile
from apps.core.models import Tenant, set_current_tenant
from apps.plm.models import (
    ComplianceStandard, EngineeringChangeOrder, Product, ProductCategory,
    ProductRevision,
)


@pytest.fixture
def acme(db):
    t = Tenant.objects.create(name='Acme', slug='acme', is_active=True)
    set_current_tenant(t)
    yield t
    set_current_tenant(None)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex', slug='globex', is_active=True)


@pytest.fixture
def acme_admin(acme):
    u = User.objects.create_user(
        username='admin_acme', password='pw', tenant=acme,
        is_tenant_admin=True, role='tenant_admin', email='a@a.com',
    )
    UserProfile.objects.create(user=u)
    return u


@pytest.fixture
def globex_admin(globex):
    u = User.objects.create_user(
        username='admin_globex', password='pw', tenant=globex,
        is_tenant_admin=True, role='tenant_admin', email='g@g.com',
    )
    UserProfile.objects.create(user=u)
    return u


@pytest.fixture
def client_acme(acme_admin):
    c = Client()
    c.force_login(acme_admin)
    return c


@pytest.fixture
def client_globex(globex_admin):
    c = Client()
    c.force_login(globex_admin)
    return c


@pytest.fixture
def category(acme):
    return ProductCategory.objects.create(tenant=acme, code='CMP', name='Components')


@pytest.fixture
def product(acme, category):
    return Product.objects.create(
        tenant=acme, sku='SKU-T001', name='Test Widget',
        category=category, product_type='component', status='active',
    )


@pytest.fixture
def revision(acme, product):
    return ProductRevision.objects.create(
        tenant=acme, product=product, revision_code='A', status='active',
    )


@pytest.fixture
def other_product(acme, category):
    return Product.objects.create(
        tenant=acme, sku='SKU-OTHER', name='Other Widget',
        category=category, product_type='component', status='active',
    )


@pytest.fixture
def other_revision(acme, other_product):
    return ProductRevision.objects.create(
        tenant=acme, product=other_product, revision_code='A', status='active',
    )


@pytest.fixture
def eco(acme, acme_admin):
    return EngineeringChangeOrder.objects.create(
        tenant=acme, number='ECO-T0001', title='Test ECO',
        requested_by=acme_admin, status='draft',
    )


@pytest.fixture
def submitted_eco(acme, acme_admin):
    return EngineeringChangeOrder.objects.create(
        tenant=acme, number='ECO-T0002', title='Submitted ECO',
        requested_by=acme_admin, status='submitted',
    )


@pytest.fixture
def standard(db):
    return ComplianceStandard.objects.create(
        code='RoHS', name='RoHS', region='eu', is_active=True,
    )
