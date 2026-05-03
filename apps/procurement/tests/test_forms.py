"""Form-layer guards: L-01 unique_together, L-02 decimal bounds, L-14 per-workflow required.

Catches the regressions that crashed earlier modules into 500s on the form
layer (where Django's auto-validate_unique() can't reach a constraint that
includes the tenant column).
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.procurement import forms, models as procm


@pytest.mark.django_db
class TestSupplierForm:
    def test_unique_code_per_tenant_via_form(self, acme, supplier):
        f = forms.SupplierForm(
            data={'code': 'SUP1', 'name': 'Dup', 'currency': 'USD',
                  'risk_rating': 'low', 'is_active': True, 'is_approved': False},
            tenant=acme,
        )
        assert not f.is_valid()
        assert 'code' in f.errors


@pytest.mark.django_db
class TestPOLineForm:
    def test_quantity_zero_rejected(self, acme):
        f = forms.PurchaseOrderLineForm(
            data={'description': 'x', 'quantity': '0',
                  'unit_of_measure': 'EA', 'unit_price': '5.00',
                  'tax_pct': '0', 'discount_pct': '0'},
            tenant=acme,
        )
        assert not f.is_valid()


@pytest.mark.django_db
class TestSupplierQuotationForm:
    def test_one_quote_per_rfq_per_supplier(self, acme, supplier):
        rfq = procm.RequestForQuotation.objects.create(tenant=acme, title='T')
        procm.SupplierQuotation.objects.create(
            tenant=acme, rfq=rfq, supplier=supplier, currency='USD',
        )
        today = timezone.now().date()
        f = forms.SupplierQuotationForm(
            data={'rfq': rfq.pk, 'supplier': supplier.pk,
                  'quote_date': today.isoformat(),
                  'currency': 'USD', 'subtotal': '0', 'tax_total': '0', 'grand_total': '0'},
            tenant=acme,
        )
        assert not f.is_valid()


@pytest.mark.django_db
class TestBlanketOrderForm:
    def test_end_before_start_rejected(self, acme, supplier):
        today = timezone.now().date()
        f = forms.BlanketOrderForm(
            data={'supplier': supplier.pk,
                  'start_date': today.isoformat(),
                  'end_date': (today - timedelta(days=1)).isoformat(),
                  'currency': 'USD', 'total_committed_value': '1000'},
            tenant=acme,
        )
        assert not f.is_valid()
        assert 'end_date' in f.errors


@pytest.mark.django_db
class TestScheduleReleaseLineForm:
    def test_cumulative_consumption_capped(self, acme, supplier, cmp_product):
        today = timezone.now().date()
        bpo = procm.BlanketOrder.objects.create(
            tenant=acme, supplier=supplier,
            start_date=today, end_date=today + timedelta(days=60),
            total_committed_value=Decimal('1000'),
        )
        bol = procm.BlanketOrderLine.objects.create(
            tenant=acme, blanket_order=bpo, product=cmp_product,
            total_quantity=Decimal('10'), unit_of_measure='EA',
            unit_price=Decimal('5'),
        )
        rel = procm.ScheduleRelease.objects.create(
            tenant=acme, blanket_order=bpo, release_date=today,
        )
        f = forms.ScheduleReleaseLineForm(
            data={'blanket_order_line': bol.pk, 'quantity': '15',
                  'required_date': today.isoformat()},
            tenant=acme, release=rel,
        )
        assert not f.is_valid()
        assert 'quantity' in f.errors


@pytest.mark.django_db
class TestPOApprovalForm:
    def test_rejection_requires_comments(self, acme):
        f = forms.PurchaseOrderApprovalForm(
            data={'decision': 'rejected', 'comments': '   '},
            tenant=acme,
        )
        assert not f.is_valid()
        assert 'comments' in f.errors


@pytest.mark.django_db
class TestSupplierInvoiceForm:
    def test_invalid_attachment_extension_rejected(self, acme, supplier):
        from django.core.files.uploadedfile import SimpleUploadedFile
        today = timezone.now().date()
        f = forms.SupplierInvoiceForm(
            data={'vendor_invoice_number': 'V1', 'supplier': supplier.pk,
                  'invoice_date': today.isoformat(),
                  'currency': 'USD',
                  'subtotal': '100', 'tax_total': '10', 'grand_total': '110'},
            files={'attachment': SimpleUploadedFile('bad.exe', b'binary', content_type='application/octet-stream')},
            tenant=acme,
        )
        assert not f.is_valid()
        assert 'attachment' in f.errors

    def test_subtotal_plus_tax_must_match_grand(self, acme, supplier):
        today = timezone.now().date()
        f = forms.SupplierInvoiceForm(
            data={'vendor_invoice_number': 'V1', 'supplier': supplier.pk,
                  'invoice_date': today.isoformat(), 'currency': 'USD',
                  'subtotal': '100', 'tax_total': '10', 'grand_total': '999'},
            tenant=acme,
        )
        assert not f.is_valid()
        assert 'grand_total' in f.errors


@pytest.mark.django_db
class TestInvoiceWorkflowForm:
    def test_paid_requires_payment_reference(self):
        f = forms.SupplierInvoiceWorkflowForm(
            data={'payment_reference': '   '}, action='paid',
        )
        assert not f.is_valid()
        assert 'payment_reference' in f.errors
