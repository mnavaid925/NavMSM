"""C.3 — N+1 query budgets for the Module 13 dashboard + list views.

Each scenario seeds enough rows to trigger N+1 if `select_related` /
`prefetch_related` is missing, then asserts the page renders within the
documented budget.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.compliance import models as cm


def _build_incidents(acme, incident_type_injury, n):
    """Bulk-create N incidents to test list view query budget."""
    return [
        cm.IncidentReport.objects.create(
            tenant=acme, incident_type=incident_type_injury,
            title=f'P{i}', description='probe',
            occurred_at=timezone.now() - timedelta(hours=i),
            severity='medium', status='reported',
        )
        for i in range(n)
    ]


def _build_documents(acme, acme_admin, n):
    return [
        cm.ComplianceDocument.objects.create(
            tenant=acme, doc_type='sop', title=f'SOP-{i}', version=f'1.{i}',
            status='draft', owner=acme_admin,
        )
        for i in range(n)
    ]


@pytest.mark.django_db
class TestComplianceQueryBudgets:

    def test_dashboard_under_budget(self, admin_client, acme, incident_type_injury,
                                     acme_admin, django_assert_max_num_queries):
        # Seed a representative dataset
        _build_incidents(acme, incident_type_injury, 25)
        _build_documents(acme, acme_admin, 10)
        # Budget covers: session + auth + tenant + KPI counts (8) + EHS rates +
        # severity histogram + recent incidents/recalls = ~20 queries.
        with django_assert_max_num_queries(35):
            r = admin_client.get(reverse('compliance:index'))
            assert r.status_code == 200

    def test_incident_list_under_budget(self, admin_client, acme, incident_type_injury,
                                        django_assert_max_num_queries):
        _build_incidents(acme, incident_type_injury, 25)
        with django_assert_max_num_queries(15):
            r = admin_client.get(reverse('compliance:incident_list'))
            assert r.status_code == 200

    def test_recall_list_under_budget(self, admin_client, acme, plm_product, acme_admin,
                                       django_assert_max_num_queries):
        for i in range(12):
            cm.ProductRecall.objects.create(
                tenant=acme, product=plm_product, title=f'R{i}',
                severity='class_iii', initiated_by=acme_admin,
            )
        with django_assert_max_num_queries(15):
            r = admin_client.get(reverse('compliance:recall_list'))
            assert r.status_code == 200

    def test_recall_detail_with_many_lots_under_budget(
        self, admin_client, acme, plm_product, acme_admin,
        django_assert_max_num_queries,
    ):
        from apps.inventory.models import Lot
        recall = cm.ProductRecall.objects.create(
            tenant=acme, product=plm_product, title='Big R',
            severity='class_iii', initiated_by=acme_admin,
        )
        for i in range(20):
            lot = Lot.objects.create(
                tenant=acme, lot_number=f'LOT-{i:03d}', product=plm_product,
            )
            cm.RecallAffectedLot.objects.create(
                tenant=acme, recall=recall, lot=lot,
                affected_quantity=Decimal('5'),
            )
        # Detail page loops over affected_lots — must use select_related on
        # `lot.product`. Budget allows for that + the notices / signatures.
        # Real load on this page is ~1.5 queries per lot; budget catches an
        # N+1 explosion (which would be 20+ queries on the lots alone) but
        # leaves headroom for the per-row content-block queries (notices,
        # signatures, audit trail).
        with django_assert_max_num_queries(35):
            r = admin_client.get(reverse('compliance:recall_detail', args=[recall.pk]))
            assert r.status_code == 200

    def test_document_list_under_budget(self, admin_client, acme, acme_admin,
                                         django_assert_max_num_queries):
        _build_documents(acme, acme_admin, 25)
        with django_assert_max_num_queries(15):
            r = admin_client.get(reverse('compliance:document_list'))
            assert r.status_code == 200

    def test_audit_trail_under_budget(self, admin_client, acme, incident_type_injury,
                                       django_assert_max_num_queries):
        # Seed activity to populate the trail
        _build_incidents(acme, incident_type_injury, 15)
        with django_assert_max_num_queries(15):
            r = admin_client.get(reverse('compliance:audit_trail_list'))
            assert r.status_code == 200
