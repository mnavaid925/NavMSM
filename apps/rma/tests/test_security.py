"""Security tests for Module 18 - Returns & RMA.

Covers:
    * Multi-tenant IDOR: cross-tenant detail URLs return 404 (every model).
    * RBAC matrix: staff (non-admin) users blocked from workflow + delete.
    * Anonymous access redirects to login on every list URL.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


pytestmark = [pytest.mark.django_db, pytest.mark.security]


# ---------------------------------------------------------------------------
# Multi-tenant IDOR
# ---------------------------------------------------------------------------

def _tenant_b_admin(tenant_b):
    User = get_user_model()
    return User.objects.create_user(
        username='admin_b', password='pw', tenant=tenant_b, is_tenant_admin=True,
    )


def test_cross_tenant_rma_request_returns_404(client, tenant_a, tenant_b, customer):
    from apps.rma.models import RMARequest
    # Object owned by tenant_a
    rma = RMARequest.objects.create(tenant=tenant_a, customer=customer)
    # Logged in as tenant_b user
    client.force_login(_tenant_b_admin(tenant_b))
    resp = client.get(reverse('rma:request_detail', kwargs={'pk': rma.pk}))
    assert resp.status_code == 404


def test_cross_tenant_repair_returns_404(client, tenant_a, tenant_b, product):
    from apps.rma.models import RepairOrder
    ro = RepairOrder.objects.create(tenant=tenant_a, product=product)
    client.force_login(_tenant_b_admin(tenant_b))
    resp = client.get(reverse('rma:repair_detail', kwargs={'pk': ro.pk}))
    assert resp.status_code == 404


def test_cross_tenant_warranty_registration_returns_404(
    client, tenant_a, tenant_b, product, customer, policy,
):
    from apps.rma.models import WarrantyRegistration
    from datetime import date
    reg = WarrantyRegistration.objects.create(
        tenant=tenant_a, product=product, customer=customer, policy=policy,
        purchase_date=date.today(), start_date=date.today(),
    )
    client.force_login(_tenant_b_admin(tenant_b))
    resp = client.get(reverse('rma:registration_detail', kwargs={'pk': reg.pk}))
    assert resp.status_code == 404


def test_cross_tenant_analysis_returns_404(
    client, tenant_a, tenant_b, customer, product, reason,
):
    from apps.rma.models import ReturnAnalysis, RMALine, RMARequest
    rma = RMARequest.objects.create(tenant=tenant_a, customer=customer)
    line = RMALine.objects.create(
        tenant=tenant_a, rma=rma, product=product, reason=reason,
        quantity=Decimal('1'), unit_price=Decimal('1'),
        condition_reported='defective',
    )
    analysis = ReturnAnalysis.objects.create(tenant=tenant_a, rma_line=line)
    client.force_login(_tenant_b_admin(tenant_b))
    resp = client.get(reverse('rma:analysis_detail', kwargs={'pk': analysis.pk}))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Anonymous redirects to login
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('url_name', [
    'rma:index', 'rma:request_list', 'rma:receipt_list', 'rma:repair_list',
    'rma:policy_list', 'rma:registration_list', 'rma:claim_list',
    'rma:analysis_list', 'rma:chargeback_list',
])
def test_anonymous_user_redirected_to_login(client, url_name):
    resp = client.get(reverse(url_name))
    assert resp.status_code in (301, 302)


# ---------------------------------------------------------------------------
# RBAC: staff (non-admin) blocked from workflow / delete  (L-10)
# ---------------------------------------------------------------------------

def test_staff_cannot_submit_rma(client, rma_request, staff_user):
    """Non-admin staff POSTing the submit URL must NOT advance status."""
    client.force_login(staff_user)
    resp = client.post(reverse('rma:request_submit', kwargs={'pk': rma_request.pk}))
    assert resp.status_code == 302  # redirected (to rma:index)
    rma_request.refresh_from_db()
    assert rma_request.status == 'draft'  # unchanged


def test_staff_cannot_approve_rma(client, rma_request, staff_user):
    rma_request.status = 'submitted'
    rma_request.save()
    client.force_login(staff_user)
    resp = client.post(
        reverse('rma:request_approve', kwargs={'pk': rma_request.pk}),
        data={'notes': 'x'},
    )
    assert resp.status_code == 302
    rma_request.refresh_from_db()
    assert rma_request.status == 'submitted'  # NOT approved


def test_staff_cannot_delete_rma(client, rma_request, staff_user):
    from apps.rma.models import RMARequest
    client.force_login(staff_user)
    resp = client.post(reverse('rma:request_delete', kwargs={'pk': rma_request.pk}))
    assert resp.status_code == 302
    assert RMARequest.objects.filter(pk=rma_request.pk).exists()


def test_staff_cannot_complete_repair(client, tenant_a, product, staff_user):
    from apps.rma.models import RepairOrder
    ro = RepairOrder.objects.create(
        tenant=tenant_a, product=product, status='in_progress',
    )
    client.force_login(staff_user)
    resp = client.post(
        reverse('rma:repair_complete', kwargs={'pk': ro.pk}),
        data={'resolution_notes': 'staff attempt'},
    )
    assert resp.status_code == 302
    ro.refresh_from_db()
    assert ro.status == 'in_progress'  # NOT completed


def test_staff_cannot_transition_chargeback(
    client, tenant_a, supplier, product, customer, reason, staff_user,
):
    from apps.rma.models import (
        ReturnAnalysis, RMALine, RMARequest, SupplierChargeback,
    )
    rma = RMARequest.objects.create(tenant=tenant_a, customer=customer)
    line = RMALine.objects.create(
        tenant=tenant_a, rma=rma, product=product, reason=reason,
        quantity=Decimal('1'), unit_price=Decimal('1'),
        condition_reported='defective',
    )
    analysis = ReturnAnalysis.objects.create(tenant=tenant_a, rma_line=line)
    cb = SupplierChargeback.objects.create(
        tenant=tenant_a, analysis=analysis, supplier=supplier,
        amount=Decimal('100'),
    )
    client.force_login(staff_user)
    resp = client.post(
        reverse('rma:chargeback_transition', kwargs={'pk': cb.pk}),
        data={'to_status': 'pending'},
    )
    assert resp.status_code == 302
    cb.refresh_from_db()
    assert cb.status == 'draft'  # unchanged
