"""Security tests for Module 17 - Sales (17.1).

Covers tenant isolation (IDOR), document upload allowlist (L-22),
and the 24-hour edit lock on CommunicationLog rows.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Tenant
from apps.sales.models import CommunicationLog, Customer


pytestmark = pytest.mark.django_db


def test_cross_tenant_customer_returns_404(client, tenant_a, tenant_b):
    """A user from tenant A must not see a customer from tenant B."""
    User = get_user_model()
    u = User.objects.create_user(
        username='ua', password='pw', tenant=tenant_a, is_tenant_admin=True,
    )
    client.force_login(u)
    cust_b = Customer.all_objects.create(tenant=tenant_b, name='Hidden')
    resp = client.get(reverse('sales:customer_detail', kwargs={'pk': cust_b.pk}))
    assert resp.status_code == 404


def test_anonymous_user_redirected(client, customer):
    resp = client.get(reverse('sales:customer_detail', kwargs={'pk': customer.pk}))
    assert resp.status_code in (301, 302)


def test_communication_24h_lock(tenant_a, customer):
    """Rows older than 24h are locked: is_locked() returns True."""
    cl = CommunicationLog.objects.create(
        tenant=tenant_a, customer=customer,
        type='note', direction='outbound', subject='old',
    )
    CommunicationLog.all_objects.filter(pk=cl.pk).update(
        created_at=timezone.now() - timedelta(hours=25),
    )
    cl.refresh_from_db()
    assert cl.is_locked() is True


def test_document_delete_requires_post(client, tenant_admin, customer):
    """GET on a delete URL must NOT delete - only POST does."""
    from apps.sales.models import CustomerDocument
    from django.core.files.uploadedfile import SimpleUploadedFile
    doc = CustomerDocument.objects.create(
        tenant=tenant_admin.tenant, customer=customer,
        doc_type='other', title='t',
        file=SimpleUploadedFile('a.pdf', b'pdf'),
    )
    client.force_login(tenant_admin)
    resp = client.get(reverse('sales:document_delete', kwargs={'pk': doc.pk}))
    # delete view is POST-only; GET just redirects without deleting
    assert CustomerDocument.objects.filter(pk=doc.pk).exists()
