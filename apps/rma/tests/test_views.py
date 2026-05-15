"""HTTP CRUD smoke tests for Module 18 - Returns & RMA views.

Every list and create page renders 200 for an authenticated tenant
admin. Workflow transitions move state through the legal path. Filters
narrow the queryset.
"""
from decimal import Decimal

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_client(client, tenant_admin):
    client.force_login(tenant_admin)
    return client


# ---- List pages all 200 ----

@pytest.mark.parametrize('url_name', [
    'rma:index',
    'rma:reason_list', 'rma:request_list', 'rma:receipt_list', 'rma:repair_list',
    'rma:policy_list', 'rma:registration_list', 'rma:claim_list',
    'rma:failure_mode_list', 'rma:root_cause_list',
    'rma:analysis_list', 'rma:chargeback_list',
])
def test_list_pages_render_200(auth_client, url_name):
    resp = auth_client.get(reverse(url_name))
    assert resp.status_code == 200


# ---- Create pages 200 ----

@pytest.mark.parametrize('url_name', [
    'rma:reason_create', 'rma:request_create', 'rma:receipt_create',
    'rma:repair_create', 'rma:policy_create', 'rma:registration_create',
    'rma:claim_create', 'rma:failure_mode_create', 'rma:root_cause_create',
    'rma:analysis_create', 'rma:chargeback_create',
])
def test_create_pages_render_200(auth_client, url_name):
    resp = auth_client.get(reverse(url_name))
    assert resp.status_code == 200


# ---- POST create ----

def test_create_reason_via_post(auth_client, tenant_a):
    from apps.rma.models import RMAReason
    resp = auth_client.post(reverse('rma:reason_create'), data={
        'name': 'POST Reason', 'category': 'other',
        'description': 'x', 'is_active': 'on',
    })
    assert resp.status_code == 302
    assert RMAReason.objects.filter(tenant=tenant_a, name='POST Reason').exists()


def test_create_failure_mode_via_post(auth_client, tenant_a):
    from apps.rma.models import FailureMode
    resp = auth_client.post(reverse('rma:failure_mode_create'), data={
        'name': 'POST FM', 'category': 'electrical',
        'description': '', 'is_active': 'on',
    })
    assert resp.status_code == 302
    assert FailureMode.objects.filter(tenant=tenant_a, name='POST FM').exists()


# ---- RMA workflow happy path ----

def test_rma_submit_and_approve_workflow(auth_client, rma_request, tenant_a):
    from apps.rma.models import RMAApproval, ReturnReceipt
    resp = auth_client.post(reverse('rma:request_submit', kwargs={'pk': rma_request.pk}))
    assert resp.status_code == 302
    rma_request.refresh_from_db()
    assert rma_request.status == 'submitted'
    assert RMAApproval.objects.filter(rma=rma_request, action='submit').exists()

    resp = auth_client.post(
        reverse('rma:request_approve', kwargs={'pk': rma_request.pk}),
        data={'notes': 'approved in test'},
    )
    assert resp.status_code == 302
    rma_request.refresh_from_db()
    assert rma_request.status == 'approved'
    # Signal drafted a receipt.
    assert ReturnReceipt.objects.filter(rma=rma_request).exists()


def test_rma_reject_requires_notes(auth_client, rma_request):
    """A rejection POST without a notes payload must NOT change status."""
    rma_request.status = 'submitted'
    rma_request.save()
    resp = auth_client.post(
        reverse('rma:request_reject', kwargs={'pk': rma_request.pk}),
        data={'notes': ''},
    )
    assert resp.status_code == 302
    rma_request.refresh_from_db()
    assert rma_request.status == 'submitted'  # still submitted


def test_rma_reject_with_notes_marks_rejected(auth_client, rma_request):
    rma_request.status = 'submitted'
    rma_request.save()
    resp = auth_client.post(
        reverse('rma:request_reject', kwargs={'pk': rma_request.pk}),
        data={'notes': 'failed inspection'},
    )
    assert resp.status_code == 302
    rma_request.refresh_from_db()
    assert rma_request.status == 'rejected'
    assert 'failed inspection' in rma_request.decision_notes


# ---- Repair complete requires resolution notes ----

def test_repair_complete_requires_resolution_notes(auth_client, tenant_a, product):
    from apps.rma.models import RepairOrder
    ro = RepairOrder.objects.create(
        tenant=tenant_a, product=product, status='in_progress',
    )
    resp = auth_client.post(
        reverse('rma:repair_complete', kwargs={'pk': ro.pk}),
        data={'resolution_notes': ''},
    )
    assert resp.status_code == 302
    ro.refresh_from_db()
    assert ro.status == 'in_progress'  # NOT completed without notes


def test_repair_complete_with_notes(auth_client, tenant_a, product):
    from apps.rma.models import RepairOrder
    ro = RepairOrder.objects.create(
        tenant=tenant_a, product=product, status='in_progress',
    )
    resp = auth_client.post(
        reverse('rma:repair_complete', kwargs={'pk': ro.pk}),
        data={'resolution_notes': 'replaced power supply'},
    )
    assert resp.status_code == 302
    ro.refresh_from_db()
    assert ro.status == 'completed'
    assert 'replaced' in ro.resolution_notes


# ---- Chargeback transition view ----

def test_chargeback_transition_legal(
    auth_client, tenant_a, supplier, product, customer, reason,
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
    resp = auth_client.post(
        reverse('rma:chargeback_transition', kwargs={'pk': cb.pk}),
        data={'to_status': 'pending'},
    )
    assert resp.status_code == 302
    cb.refresh_from_db()
    assert cb.status == 'pending'


# ---- Filters narrow the queryset ----

def test_request_list_status_filter_narrows(auth_client, rma_request):
    """Pending-approval filter excludes the draft fixture."""
    resp = auth_client.get(reverse('rma:request_list'), {'status': 'submitted'})
    assert resp.status_code == 200
    assert rma_request.code.encode() not in resp.content


def test_request_list_status_filter_matches(auth_client, rma_request):
    """Draft filter includes the draft fixture."""
    resp = auth_client.get(reverse('rma:request_list'), {'status': 'draft'})
    assert resp.status_code == 200
    assert rma_request.code.encode() in resp.content
