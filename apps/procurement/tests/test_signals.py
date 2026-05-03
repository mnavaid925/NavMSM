"""Audit-log emission + cross-module SupplierMetricEvent hooks."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.tenants.models import TenantAuditLog
from apps.procurement import models as procm


@pytest.mark.django_db
class TestPOAuditSignals:
    def test_creation_audited(self, acme, supplier, acme_admin):
        TenantAuditLog.objects.filter(tenant=acme).delete()
        po = procm.PurchaseOrder.objects.create(
            tenant=acme, supplier=supplier, currency='USD', status='draft',
            created_by=acme_admin,
        )
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='procurement.po.created',
            target_type='PurchaseOrder', target_id=str(po.pk),
        ).exists()

    def test_status_change_audited(self, acme, po):
        TenantAuditLog.objects.filter(tenant=acme).delete()
        po.status = 'submitted'
        po.save()
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='procurement.po.submitted',
        ).exists()


@pytest.mark.django_db
class TestSupplierAuditSignals:
    def test_approval_change_audited(self, acme, supplier):
        TenantAuditLog.objects.filter(tenant=acme).delete()
        supplier.is_approved = False
        supplier.save()
        assert TenantAuditLog.objects.filter(
            tenant=acme, action='procurement.supplier.approval_changed',
        ).exists()


@pytest.mark.django_db
class TestCrossModuleGRNHook:
    def test_grn_completed_emits_metric_event(self, acme, supplier, po, cmp_product):
        """When inventory GRN flips to completed AND links to a PO, emit metric."""
        from apps.inventory.models import GoodsReceiptNote, Warehouse
        wh = Warehouse.objects.create(
            tenant=acme, code='W1', name='W1', is_default=True, is_active=True,
        )
        # Approve the PO so the linkage is meaningful (and required_date is set)
        po.required_date = timezone.now().date() - timedelta(days=2)  # so receipt is "late"
        po.status = 'received'
        po.save()

        grn = GoodsReceiptNote.objects.create(
            tenant=acme, warehouse=wh,
            supplier=supplier, purchase_order=po,
            received_date=timezone.now().date(),
            status='draft',
        )
        # Flip to completed
        grn.status = 'completed'
        grn.save()

        events = procm.SupplierMetricEvent.objects.filter(
            tenant=acme, supplier=supplier, event_type='po_received_late',
        )
        assert events.exists()

    def test_grn_without_po_skipped(self, acme):
        from apps.inventory.models import GoodsReceiptNote, Warehouse
        wh = Warehouse.objects.create(
            tenant=acme, code='W2', name='W2', is_default=True, is_active=True,
        )
        before = procm.SupplierMetricEvent.objects.filter(tenant=acme).count()
        grn = GoodsReceiptNote.objects.create(
            tenant=acme, warehouse=wh,
            supplier_name='Free text supplier',  # no FK
            received_date=timezone.now().date(),
            status='draft',
        )
        grn.status = 'completed'
        grn.save()
        after = procm.SupplierMetricEvent.objects.filter(tenant=acme).count()
        assert after == before


@pytest.mark.django_db
class TestCrossModuleIQCHook:
    def test_iqc_rejected_emits_quality_fail(self, acme, supplier, cmp_product):
        from apps.qms.models import IncomingInspection
        iqc = IncomingInspection.objects.create(
            tenant=acme, product=cmp_product,
            supplier=supplier,
            received_qty=Decimal('100'),
            sample_size=10, accept_number=1, reject_number=2,
            status='pending',
        )
        iqc.status = 'rejected'
        iqc.save()
        assert procm.SupplierMetricEvent.objects.filter(
            tenant=acme, supplier=supplier, event_type='quality_fail',
        ).exists()

    def test_iqc_accepted_emits_quality_pass(self, acme, supplier, cmp_product):
        from apps.qms.models import IncomingInspection
        iqc = IncomingInspection.objects.create(
            tenant=acme, product=cmp_product,
            supplier=supplier,
            received_qty=Decimal('100'),
            sample_size=10, accept_number=1, reject_number=2,
            status='pending',
        )
        iqc.status = 'accepted'
        iqc.save()
        assert procm.SupplierMetricEvent.objects.filter(
            tenant=acme, supplier=supplier, event_type='quality_pass',
        ).exists()
