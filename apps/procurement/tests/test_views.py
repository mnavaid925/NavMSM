"""View-layer smoke tests: list / create / detail flows for each sub-module."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.procurement import models as procm


@pytest.mark.django_db
class TestSupplierViews:
    def test_list_renders(self, admin_client, supplier):
        r = admin_client.get(reverse('procurement:supplier_list'))
        assert r.status_code == 200
        assert b'SUP1' in r.content

    def test_create_get(self, admin_client):
        r = admin_client.get(reverse('procurement:supplier_create'))
        assert r.status_code == 200

    def test_create_post(self, admin_client, acme):
        r = admin_client.post(reverse('procurement:supplier_create'), data={
            'code': 'NEW1', 'name': 'New supplier', 'currency': 'USD',
            'risk_rating': 'low', 'is_active': 'on', 'is_approved': '',
        })
        assert r.status_code == 302
        assert procm.Supplier.all_objects.filter(tenant=acme, code='NEW1').exists()

    def test_detail_renders(self, admin_client, supplier):
        r = admin_client.get(reverse('procurement:supplier_detail', args=[supplier.pk]))
        assert r.status_code == 200


@pytest.mark.django_db
class TestPOWorkflow:
    def test_submit_draft_to_submitted(self, admin_client, po):
        r = admin_client.post(reverse('procurement:po_submit', args=[po.pk]))
        assert r.status_code == 302
        po.refresh_from_db()
        assert po.status == 'submitted'

    def test_approve_then_acknowledge(self, admin_client, po, acme_admin):
        po.status = 'submitted'
        po.save()
        admin_client.post(reverse('procurement:po_approve', args=[po.pk]))
        po.refresh_from_db()
        assert po.status == 'approved'
        admin_client.post(reverse('procurement:po_acknowledge', args=[po.pk]))
        po.refresh_from_db()
        assert po.status == 'acknowledged'

    def test_revise_resets_to_draft_with_snapshot(self, admin_client, po, acme):
        po.status = 'submitted'
        po.save()
        r = admin_client.post(
            reverse('procurement:po_revise', args=[po.pk]),
            data={'change_summary': 'fix qty'},
        )
        assert r.status_code == 302
        po.refresh_from_db()
        assert po.status == 'draft'
        assert procm.PurchaseOrderRevision.all_objects.filter(po=po).count() == 1


@pytest.mark.django_db
class TestRFQWorkflow:
    def test_create_then_issue(self, admin_client, acme, supplier, cmp_product):
        # Create RFQ via view
        r = admin_client.post(reverse('procurement:rfq_create'), data={
            'title': 'My RFQ', 'description': 'desc', 'currency': 'USD',
            'round_number': '1',
        })
        assert r.status_code == 302
        rfq = procm.RequestForQuotation.all_objects.filter(tenant=acme).first()
        assert rfq is not None
        # Add a line + invite supplier directly (skip form rendering details)
        procm.RFQLine.objects.create(
            tenant=acme, rfq=rfq, product=cmp_product,
            quantity=Decimal('10'), unit_of_measure='EA',
        )
        procm.RFQSupplier.objects.create(tenant=acme, rfq=rfq, supplier=supplier)
        # Issue
        r2 = admin_client.post(reverse('procurement:rfq_issue', args=[rfq.pk]))
        assert r2.status_code == 302
        rfq.refresh_from_db()
        assert rfq.status == 'issued'

    def test_issue_blocked_without_lines(self, admin_client, acme):
        rfq = procm.RequestForQuotation.objects.create(tenant=acme, title='No lines')
        r = admin_client.post(reverse('procurement:rfq_issue', args=[rfq.pk]))
        assert r.status_code == 302
        rfq.refresh_from_db()
        assert rfq.status == 'draft'


@pytest.mark.django_db
class TestInvoicePayment:
    def test_pay_requires_reference(self, admin_client, acme, supplier):
        today = timezone.now().date()
        inv = procm.SupplierInvoice.objects.create(
            tenant=acme, vendor_invoice_number='V1', supplier=supplier,
            invoice_date=today, currency='USD',
            subtotal=Decimal('100'), tax_total=Decimal('10'), grand_total=Decimal('110'),
            status='approved',
        )
        # Without reference - rejected
        r = admin_client.post(reverse('procurement:invoice_pay', args=[inv.pk]))
        inv.refresh_from_db()
        assert inv.status == 'approved'
        # With reference - paid
        r2 = admin_client.post(
            reverse('procurement:invoice_pay', args=[inv.pk]),
            data={'payment_reference': 'PAY-9999'},
        )
        inv.refresh_from_db()
        assert inv.status == 'paid'
        assert inv.payment_reference == 'PAY-9999'


@pytest.mark.django_db
class TestSupplierPortalScope:
    def test_portal_dashboard_renders(self, supplier_user_client):
        r = supplier_user_client.get(reverse('procurement:portal_dashboard'))
        assert r.status_code == 200

    def test_portal_only_shows_own_supplier_pos(
        self, supplier_user_client, supplier, supplier2, cmp_product, acme, acme_admin,
    ):
        # PO for the supplier the portal user is attached to
        own_po = procm.PurchaseOrder.objects.create(
            tenant=acme, supplier=supplier, currency='USD', status='approved',
            created_by=acme_admin,
        )
        # PO for a different supplier
        other_po = procm.PurchaseOrder.objects.create(
            tenant=acme, supplier=supplier2, currency='USD', status='approved',
            created_by=acme_admin,
        )
        r = supplier_user_client.get(reverse('procurement:portal_pos'))
        assert r.status_code == 200
        assert own_po.po_number.encode() in r.content
        assert other_po.po_number.encode() not in r.content

    def test_internal_user_blocked_from_portal(self, admin_client):
        r = admin_client.get(reverse('procurement:portal_dashboard'))
        # Internal admin is NOT role='supplier' so should be redirected.
        assert r.status_code == 302


@pytest.mark.django_db
class TestDashboard:
    def test_dashboard_renders(self, admin_client, supplier):
        r = admin_client.get(reverse('procurement:index'))
        assert r.status_code == 200
