"""Module 9 model invariants and validators."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.procurement import models as procm


@pytest.mark.django_db
class TestSupplier:
    def test_str(self, supplier):
        assert 'SUP1' in str(supplier)

    def test_unique_code_per_tenant(self, acme, supplier):
        with pytest.raises(Exception):
            procm.Supplier.all_objects.create(
                tenant=acme, code='SUP1', name='dup',
            )


@pytest.mark.django_db
class TestPurchaseOrder:
    def test_auto_number(self, po):
        assert po.po_number.startswith('PUR-')

    def test_recompute_totals(self, po):
        # 10 * 5.00 = 50.00 subtotal, no tax/discount
        assert po.subtotal == Decimal('50.00')
        assert po.grand_total == Decimal('50.00')

    def test_quantity_min_validator(self, acme, po):
        line = procm.PurchaseOrderLine(
            tenant=acme, po=po, description='bad', quantity=Decimal('0'),
            unit_of_measure='EA', unit_price=Decimal('1'),
        )
        # full_clean enforces validators
        with pytest.raises(ValidationError):
            line.full_clean()

    def test_tax_pct_max_100(self, acme, po):
        line = procm.PurchaseOrderLine(
            tenant=acme, po=po, description='bad', quantity=Decimal('1'),
            unit_of_measure='EA', unit_price=Decimal('1'), tax_pct=Decimal('150'),
        )
        with pytest.raises(ValidationError):
            line.full_clean()

    def test_is_editable_for_draft_only(self, po):
        assert po.is_editable() is True
        po.status = 'approved'
        po.save(update_fields=['status'])
        assert po.is_editable() is False


@pytest.mark.django_db
class TestRFQ:
    def test_auto_number(self, acme):
        rfq = procm.RequestForQuotation.objects.create(
            tenant=acme, title='X', currency='USD',
        )
        assert rfq.rfq_number.startswith('RFQ-')


@pytest.mark.django_db
class TestQuotation:
    def test_auto_number_and_unique_per_rfq(self, acme, supplier):
        rfq = procm.RequestForQuotation.objects.create(tenant=acme, title='X')
        q1 = procm.SupplierQuotation.objects.create(
            tenant=acme, rfq=rfq, supplier=supplier, currency='USD',
        )
        assert q1.quote_number.startswith('QUO-')
        with pytest.raises(Exception):
            procm.SupplierQuotation.all_objects.create(
                tenant=acme, rfq=rfq, supplier=supplier, currency='USD',
            )


@pytest.mark.django_db
class TestBlanketOrder:
    def test_auto_number(self, acme, supplier):
        today = timezone.now().date()
        b = procm.BlanketOrder.objects.create(
            tenant=acme, supplier=supplier,
            start_date=today, end_date=today + timedelta(days=30),
            total_committed_value=Decimal('1000'),
        )
        assert b.bpo_number.startswith('BPO-')

    def test_remaining_value(self, acme, supplier):
        today = timezone.now().date()
        b = procm.BlanketOrder.objects.create(
            tenant=acme, supplier=supplier,
            start_date=today, end_date=today + timedelta(days=30),
            total_committed_value=Decimal('1000'),
            consumed_value=Decimal('300'),
        )
        assert b.remaining_value == Decimal('700')


@pytest.mark.django_db
class TestSupplierInvoice:
    def test_auto_number(self, acme, supplier):
        today = timezone.now().date()
        inv = procm.SupplierInvoice.objects.create(
            tenant=acme, vendor_invoice_number='V-1', supplier=supplier,
            invoice_date=today, currency='USD',
            subtotal=Decimal('100'), tax_total=Decimal('10'), grand_total=Decimal('110'),
        )
        assert inv.invoice_number.startswith('SUPINV-')

    def test_unique_vendor_invoice_per_supplier(self, acme, supplier):
        today = timezone.now().date()
        procm.SupplierInvoice.objects.create(
            tenant=acme, vendor_invoice_number='DUP', supplier=supplier,
            invoice_date=today,
        )
        with pytest.raises(Exception):
            procm.SupplierInvoice.all_objects.create(
                tenant=acme, vendor_invoice_number='DUP', supplier=supplier,
                invoice_date=today,
            )


@pytest.mark.django_db
class TestSupplierMetricEvent:
    def test_event_creation(self, acme, supplier):
        ev = procm.SupplierMetricEvent.objects.create(
            tenant=acme, supplier=supplier,
            event_type='po_received_on_time', value=Decimal('0'),
        )
        assert 'SUP1' in str(ev)
