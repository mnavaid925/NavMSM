"""Search / Filter / Pagination edge cases.

Converts manual plan §4.8 SEARCH (TC-SEARCH-01..09), §4.9 PAGINATION
(TC-PAGE-01..05), and §4.10 FILTERS (TC-FILTER-01..10).
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.mrp.models import (
    ForecastModel, MRPException, MRPPurchaseRequisition, ScheduledReceipt,
)


# ---------------- SEARCH ----------------

@pytest.mark.django_db
class TestSearch:
    def test_empty_q_returns_all(self, admin_client, forecast_model):
        r = admin_client.get(reverse('mrp:forecast_model_list') + '?q=')
        assert r.status_code == 200
        assert forecast_model.name.encode() in r.content

    def test_single_char_match(self, admin_client, forecast_model):
        # forecast_model.name = 'SMA-3' from conftest
        r = admin_client.get(reverse('mrp:forecast_model_list') + '?q=S')
        assert r.status_code == 200
        assert forecast_model.name.encode() in r.content

    def test_no_match_empty_state(self, admin_client, forecast_model):
        r = admin_client.get(reverse('mrp:forecast_model_list') + '?q=xyzzy_nope')
        assert r.status_code == 200
        assert forecast_model.name.encode() not in r.content

    def test_special_chars_no_500(self, admin_client, acme, calc, raw_product):
        # ORM icontains escapes %, _, etc internally — no SQL injection risk
        # and no 500 even on rude input.
        for payload in ["'", '%', '_', '<>', "' OR 1=1--"]:
            r = admin_client.get(reverse('mrp:pr_list') + f'?q={payload}')
            assert r.status_code == 200, f'q={payload!r} failed'

    def test_whitespace_trimmed(self, admin_client, forecast_model):
        r = admin_client.get(reverse('mrp:forecast_model_list') + '?q=%20%20SMA%20%20')
        assert r.status_code == 200
        assert forecast_model.name.encode() in r.content


# ---------------- FILTERS ----------------

@pytest.mark.django_db
class TestFilters:
    def test_fm_filter_by_method(self, admin_client, acme, forecast_model):
        ForecastModel.objects.create(
            tenant=acme, name='Naive', method='naive_seasonal',
            params={}, period_type='month', horizon_periods=12, is_active=True,
        )
        r = admin_client.get(reverse('mrp:forecast_model_list') + '?method=naive_seasonal')
        assert r.status_code == 200
        assert b'Naive' in r.content
        assert forecast_model.name.encode() not in r.content  # MA-3 hidden

    def test_fm_combined_method_and_period(self, admin_client, acme):
        ForecastModel.objects.create(
            tenant=acme, name='WK', method='moving_avg', params={},
            period_type='week', horizon_periods=4, is_active=True,
        )
        ForecastModel.objects.create(
            tenant=acme, name='MO', method='moving_avg', params={},
            period_type='month', horizon_periods=4, is_active=True,
        )
        r = admin_client.get(
            reverse('mrp:forecast_model_list') + '?method=moving_avg&period_type=month'
        )
        assert r.status_code == 200
        assert b'MO' in r.content
        # 'WK' weekly model should not appear in monthly-filter results.
        # We check that the row link is missing (subtler than substring "WK"
        # since the badge HTML for "Weekly" contains 'W'). Use the bom number-style
        # absent-check on the model edit URL instead.
        wk = ForecastModel.objects.get(tenant=acme, name='WK')
        edit_url = reverse('mrp:forecast_model_edit', args=[wk.pk])
        assert edit_url.encode() not in r.content

    def test_fm_active_filter(self, admin_client, acme, forecast_model):
        ForecastModel.objects.create(
            tenant=acme, name='Sleeping', method='moving_avg', params={},
            period_type='week', horizon_periods=4, is_active=False,
        )
        r = admin_client.get(reverse('mrp:forecast_model_list') + '?active=inactive')
        assert b'Sleeping' in r.content
        assert forecast_model.name.encode() not in r.content

    def test_pr_filter_by_status(self, admin_client, acme, calc, raw_product):
        approved = MRPPurchaseRequisition.objects.create(
            tenant=acme, pr_number='MPR-A', mrp_calculation=calc,
            product=raw_product, quantity=Decimal('1'),
            required_by_date=date.today() + timedelta(days=14),
            suggested_release_date=date.today(),
            status='approved', priority='normal',
        )
        draft = MRPPurchaseRequisition.objects.create(
            tenant=acme, pr_number='MPR-D', mrp_calculation=calc,
            product=raw_product, quantity=Decimal('1'),
            required_by_date=date.today() + timedelta(days=14),
            suggested_release_date=date.today(),
            status='draft', priority='normal',
        )
        r = admin_client.get(reverse('mrp:pr_list') + '?status=draft')
        assert b'MPR-D' in r.content
        assert b'MPR-A' not in r.content

    def test_exception_filter_by_severity(self, admin_client, acme, calc, raw_product):
        crit = MRPException.objects.create(
            tenant=acme, mrp_calculation=calc, product=raw_product,
            exception_type='no_bom', severity='critical', message='boom',
        )
        low = MRPException.objects.create(
            tenant=acme, mrp_calculation=calc, product=raw_product,
            exception_type='below_min', severity='low', message='small',
        )
        r = admin_client.get(reverse('mrp:exception_list') + '?severity=critical')
        # Match by exception detail URL since both exceptions share the same SKU.
        crit_url = reverse('mrp:exception_detail', args=[crit.pk])
        low_url = reverse('mrp:exception_detail', args=[low.pk])
        assert crit_url.encode() in r.content
        assert low_url.encode() not in r.content

    def test_receipt_filter_by_type(self, admin_client, acme, raw_product, fg_product):
        ScheduledReceipt.objects.create(
            tenant=acme, product=raw_product, receipt_type='open_po',
            quantity=Decimal('5'),
            expected_date=date.today() + timedelta(days=3),
            reference='POREF',
        )
        ScheduledReceipt.objects.create(
            tenant=acme, product=fg_product, receipt_type='planned_production',
            quantity=Decimal('1'),
            expected_date=date.today() + timedelta(days=3),
            reference='PROD',
        )
        r = admin_client.get(reverse('mrp:receipt_list') + '?receipt_type=open_po')
        assert b'POREF' in r.content
        assert b'PROD' not in r.content


# ---------------- PAGINATION ----------------

@pytest.mark.django_db
class TestPagination:
    def test_invalid_page_string_404(self, admin_client):
        # Django ListView raises Http404 on un-parseable page param.
        r = admin_client.get(reverse('mrp:pr_list') + '?page=abc')
        assert r.status_code == 404

    def test_beyond_last_page_404(self, admin_client):
        r = admin_client.get(reverse('mrp:pr_list') + '?page=99999')
        assert r.status_code == 404

    def test_filter_retained_across_pages(
        self, admin_client, acme, calc, raw_product,
    ):
        # Build > 20 draft PRs so pagination kicks in (PR list paginate_by=20).
        for i in range(22):
            MRPPurchaseRequisition.objects.create(
                tenant=acme, pr_number=f'MPR-PG{i:03d}',
                mrp_calculation=calc, product=raw_product,
                quantity=Decimal('1'),
                required_by_date=date.today() + timedelta(days=14),
                suggested_release_date=date.today(),
                status='draft', priority='normal',
            )
        # Add an approved one to be filtered out.
        MRPPurchaseRequisition.objects.create(
            tenant=acme, pr_number='MPR-APR', mrp_calculation=calc,
            product=raw_product, quantity=Decimal('1'),
            required_by_date=date.today() + timedelta(days=14),
            suggested_release_date=date.today(),
            status='approved', priority='normal',
        )
        r = admin_client.get(reverse('mrp:pr_list') + '?status=draft&page=2')
        assert r.status_code == 200
        # The approved row must NOT appear on page 2 of draft-filtered list.
        assert b'MPR-APR' not in r.content
