"""N+1 budgets for Module 14 list views and the dashboard.

Closes TC-PERF-001..004 from the SQA report. Numbers are upper bounds —
each list view should comfortably stay below.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.utility import models as U


pytestmark = [pytest.mark.django_db]


def _seed_25_consumption(acme, meter):
    now = timezone.now()
    for i in range(25):
        U.UtilityConsumption.objects.create(
            tenant=acme, meter=meter,
            period_start=now - timedelta(hours=i + 1),
            period_end=now - timedelta(hours=i),
            start_reading=Decimal(i * 100), end_reading=Decimal(i * 100 + 50),
            unit_cost=Decimal('0.12'),
        )


def test_consumption_list_n_plus_one(
    django_assert_max_num_queries, admin_client, acme, meter,
):
    _seed_25_consumption(acme, meter)
    with django_assert_max_num_queries(20):
        r = admin_client.get(reverse('utility:consumption_list'))
    assert r.status_code == 200


def test_allocation_list_n_plus_one(
    django_assert_max_num_queries, admin_client, acme, acp_open, meter,
):
    for i in range(20):
        U.UtilityAllocation.objects.create(
            tenant=acme, period=acp_open, meter=meter,
            share_pct=Decimal('100'),
            allocated_consumption=Decimal('50'),
            allocated_cost=Decimal('6'),
        )
    with django_assert_max_num_queries(20):
        r = admin_client.get(reverse('utility:allocation_list'))
    assert r.status_code == 200


def test_emission_list_n_plus_one(
    django_assert_max_num_queries, admin_client, acme, acp_open, emission_factor_grid,
):
    for i in range(15):
        U.CarbonEmission.objects.create(
            tenant=acme, period=acp_open, scope='scope_2',
            source_type='electricity_grid', source_quantity=Decimal(i + 1),
            factor=emission_factor_grid,
        )
    with django_assert_max_num_queries(20):
        r = admin_client.get(reverse('utility:emission_list'))
    assert r.status_code == 200


def test_dashboard_query_budget(
    django_assert_max_num_queries, admin_client, acme, meter,
):
    _seed_25_consumption(acme, meter)
    with django_assert_max_num_queries(35):
        r = admin_client.get(reverse('utility:index'))
    assert r.status_code == 200
