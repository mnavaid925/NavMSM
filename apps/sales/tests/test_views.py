"""Smoke + CRUD tests for Module 17 - Sales views (17.1)."""
import pytest
from django.urls import reverse


pytestmark = pytest.mark.django_db


@pytest.fixture
def client_admin(client, tenant_admin):
    client.force_login(tenant_admin)
    return client


def test_index_view(client_admin):
    resp = client_admin.get(reverse('sales:index'))
    assert resp.status_code == 200
    assert b'Sales' in resp.content


def test_customer_list_view(client_admin, customer):
    resp = client_admin.get(reverse('sales:customer_list'))
    assert resp.status_code == 200
    assert customer.name.encode() in resp.content


def test_customer_list_filters(client_admin, customer):
    """Filter params must not 500."""
    resp = client_admin.get(reverse('sales:customer_list'), {
        'q': 'ACME', 'status': 'active', 'customer_class': 'key',
    })
    assert resp.status_code == 200


def test_customer_create_view(client_admin):
    resp = client_admin.post(reverse('sales:customer_create'), {
        'name': 'New Co',
        'customer_class': 'standard',
        'currency': 'USD',
        'payment_terms': 'net30',
        'credit_limit': '0',
        'status': 'active',
    })
    assert resp.status_code in (302, 200)
    from apps.sales.models import Customer
    assert Customer.objects.filter(name='New Co').exists()


def test_customer_detail_view(client_admin, customer):
    resp = client_admin.get(reverse('sales:customer_detail', kwargs={'pk': customer.pk}))
    assert resp.status_code == 200


def test_customer_delete_redirects_to_list(client_admin, customer):
    resp = client_admin.post(reverse('sales:customer_delete', kwargs={'pk': customer.pk}))
    assert resp.status_code == 302
    from apps.sales.models import Customer
    assert not Customer.objects.filter(pk=customer.pk).exists()


def test_pricelist_list_view(client_admin, default_pricelist):
    resp = client_admin.get(reverse('sales:pricelist_list'))
    assert resp.status_code == 200
    assert default_pricelist.name.encode() in resp.content


def test_category_list_view(client_admin, category):
    resp = client_admin.get(reverse('sales:category_list'))
    assert resp.status_code == 200


def test_login_required(client):
    """Anonymous access must redirect to login."""
    resp = client.get(reverse('sales:customer_list'))
    assert resp.status_code in (302, 301)
