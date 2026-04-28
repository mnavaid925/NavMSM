"""Query-budget assertions for list pages and engine.

Catches N+1 regressions across the list views; the engine BOM-lookup budget
is asserted in test_engine.py::TestEngineBOMQueryBudgetD09.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestListPageQueryBudget:
    def test_calculation_list_under_budget(
        self, admin_client, django_assert_max_num_queries, calc,
    ):
        with django_assert_max_num_queries(15):
            r = admin_client.get(reverse('mrp:calculation_list'))
        assert r.status_code == 200

    def test_pr_list_under_budget(
        self, admin_client, django_assert_max_num_queries,
        acme, calc, raw_product,
    ):
        from apps.mrp.models import MRPPurchaseRequisition
        for i in range(15):
            MRPPurchaseRequisition.objects.create(
                tenant=acme, pr_number=f'MPR-P{i:03d}',
                mrp_calculation=calc, product=raw_product,
                quantity=Decimal('5'),
                required_by_date=date.today() + timedelta(days=14),
                suggested_release_date=date.today(),
                status='draft', priority='normal',
            )
        with django_assert_max_num_queries(15):
            r = admin_client.get(reverse('mrp:pr_list'))
        assert r.status_code == 200

    def test_inventory_list_under_budget(
        self, admin_client, django_assert_max_num_queries,
        acme, snapshot_fg, snapshot_rm,
    ):
        with django_assert_max_num_queries(15):
            r = admin_client.get(reverse('mrp:inventory_list'))
        assert r.status_code == 200

    def test_exception_list_under_budget(
        self, admin_client, django_assert_max_num_queries,
        acme, calc, raw_product,
    ):
        from apps.mrp.models import MRPException
        for i in range(20):
            MRPException.objects.create(
                tenant=acme, mrp_calculation=calc, product=raw_product,
                exception_type='late_order', severity='high', message=f'm{i}',
            )
        with django_assert_max_num_queries(15):
            r = admin_client.get(reverse('mrp:exception_list'))
        assert r.status_code == 200
