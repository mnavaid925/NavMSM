"""Model-level tests for Module 17 - Sales (17.1)."""
from decimal import Decimal

import pytest

from apps.core.models import set_current_tenant
from apps.sales.models import (
    CommunicationLog,
    Customer,
    CustomerCategory,
    CustomerContact,
    PriceList,
    PriceListItem,
)


pytestmark = pytest.mark.django_db


def test_customer_auto_code(tenant_a):
    c1 = Customer.objects.create(tenant=tenant_a, name='First')
    c2 = Customer.objects.create(tenant=tenant_a, name='Second')
    assert c1.code.startswith('CUST-')
    assert c2.code.startswith('CUST-')
    assert c1.code != c2.code


def test_customer_credit_available_property(tenant_a):
    c = Customer.objects.create(
        tenant=tenant_a, name='X',
        credit_limit=Decimal('1000'), credit_used=Decimal('250'),
    )
    assert c.credit_available == Decimal('750')


def test_pricelist_auto_code_and_default(tenant_a):
    p = PriceList.objects.create(tenant=tenant_a, name='Default')
    assert p.code.startswith('PL-')


def test_pricelist_item_unique_per_tier(tenant_a, default_pricelist):
    """Same product+tier combo must not be insertable twice."""
    from apps.plm.models import Product
    prod = Product.objects.create(
        tenant=tenant_a, name='Widget', code='WG-001',
    )
    PriceListItem.objects.create(
        tenant=tenant_a, price_list=default_pricelist,
        product=prod, unit_price=Decimal('10'), min_qty=Decimal('1'),
    )
    with pytest.raises(Exception):
        PriceListItem.objects.create(
            tenant=tenant_a, price_list=default_pricelist,
            product=prod, unit_price=Decimal('20'), min_qty=Decimal('1'),
        )


def test_communication_auto_code_and_lock_window(tenant_a, customer):
    cl = CommunicationLog.objects.create(
        tenant=tenant_a, customer=customer,
        type='note', direction='outbound', subject='hi',
    )
    assert cl.code.startswith('COMM-')
    assert cl.is_locked() is False  # just created


def test_tenant_isolation(tenant_a, tenant_b):
    """A Customer in tenant_b must not appear under tenant_a scope."""
    Customer.all_objects.create(tenant=tenant_b, name='Cross-tenant')
    set_current_tenant(tenant_a)
    assert not Customer.objects.filter(name='Cross-tenant').exists()
    set_current_tenant(None)


def test_customer_category_self_fk(tenant_a):
    root = CustomerCategory.objects.create(tenant=tenant_a, name='Industry')
    child = CustomerCategory.objects.create(
        tenant=tenant_a, name='Automotive', parent=root,
    )
    assert child.parent_id == root.id
    assert root.children.count() == 1


def test_customer_contact_primary_flag(tenant_a, customer):
    a = CustomerContact.objects.create(
        tenant=tenant_a, customer=customer,
        full_name='Alice', is_primary=True,
    )
    b = CustomerContact.objects.create(
        tenant=tenant_a, customer=customer,
        full_name='Bob', is_primary=False,
    )
    assert a.is_primary and not b.is_primary
