"""Customer-portal scoping tests (17.5)."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.core.models import Tenant
from apps.sales.models import Customer, SalesOrder


pytestmark = pytest.mark.django_db


@pytest.fixture
def portal_user(tenant_a, customer):
    User = get_user_model()
    u = User.objects.create_user(
        username='portal_a', password='pw', email='portal_a@example.com',
        tenant=tenant_a, role='customer',
    )
    u.customer_company = customer
    u.save()
    return u


def test_portal_dashboard_visible(client, portal_user):
    client.force_login(portal_user)
    resp = client.get(reverse('sales:portal_dashboard'))
    assert resp.status_code == 200


def test_portal_redirects_unlinked_user(client, tenant_a):
    """A user without customer_company set is bounced to the main dashboard."""
    User = get_user_model()
    u = User.objects.create_user(
        username='no_link', password='pw', tenant=tenant_a, role='customer',
    )
    client.force_login(u)
    resp = client.get(reverse('sales:portal_dashboard'))
    assert resp.status_code in (302, 301)


def test_portal_cannot_see_other_customer_order(client, tenant_a, portal_user, customer):
    """An order belonging to a different customer must 404."""
    other = Customer.objects.create(
        tenant=tenant_a, name='Other Co',
    )
    other_so = SalesOrder.objects.create(tenant=tenant_a, customer=other)
    client.force_login(portal_user)
    resp = client.get(reverse('sales:portal_order_detail', kwargs={'pk': other_so.pk}))
    assert resp.status_code == 404


def test_portal_sees_own_order(client, tenant_a, portal_user, customer):
    so = SalesOrder.objects.create(tenant=tenant_a, customer=customer)
    client.force_login(portal_user)
    resp = client.get(reverse('sales:portal_order_detail', kwargs={'pk': so.pk}))
    assert resp.status_code == 200
    assert so.code.encode() in resp.content


def test_portal_invoice_list_scoped(client, tenant_a, portal_user, customer):
    from apps.sales.models import SalesInvoice
    so = SalesOrder.objects.create(tenant=tenant_a, customer=customer)
    inv = SalesInvoice.objects.create(
        tenant=tenant_a, sales_order=so, status='issued',
        grand_total=Decimal('100'),
    )
    # Other customer's invoice
    other = Customer.objects.create(tenant=tenant_a, name='Other')
    other_so = SalesOrder.objects.create(tenant=tenant_a, customer=other)
    SalesInvoice.objects.create(
        tenant=tenant_a, sales_order=other_so, status='issued',
        grand_total=Decimal('99999'),
    )
    client.force_login(portal_user)
    resp = client.get(reverse('sales:portal_invoice_list'))
    assert resp.status_code == 200
    assert inv.code.encode() in resp.content
    assert b'99999' not in resp.content
