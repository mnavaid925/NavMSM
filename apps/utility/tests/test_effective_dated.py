"""Regression guards for D-01 / D-02: services must respect effective_to.

Both tests are expected to FAIL against the pre-patch code; they pass once
``_resolve_unit_cost`` and ``_resolve_factor`` honor ``effective_to``.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.utility import models as U
from apps.utility.services import carbon as carbon_svc
from apps.utility.services import meters as meter_svc


pytestmark = [pytest.mark.django_db, pytest.mark.security]


def test_resolve_unit_cost_skips_expired_tariff(acme, utility_type_electricity, meter):
    """D-01: an expired but is_active=True tariff must NOT be used."""
    today = date.today()
    U.UtilityTariff.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        name='Expired', effective_from=today - timedelta(days=400),
        effective_to=today - timedelta(days=30),
        flat_rate=Decimal('0.10'), currency='USD', is_active=True,
    )
    rate = meter_svc._resolve_unit_cost(meter, timezone.now())
    assert rate == Decimal('0'), (
        f'Expired tariff should not be selected; got {rate}.'
    )


def test_resolve_unit_cost_uses_open_ended_tariff(acme, utility_type_electricity, meter):
    """An open-ended tariff (effective_to=NULL) is always valid."""
    today = date.today()
    U.UtilityTariff.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        name='Open-ended', effective_from=today - timedelta(days=10),
        effective_to=None,
        flat_rate=Decimal('0.15'), currency='USD', is_active=True,
    )
    rate = meter_svc._resolve_unit_cost(meter, timezone.now())
    assert rate == Decimal('0.15')


def test_resolve_factor_skips_expired_factor(acme):
    """D-02: an expired but is_active=True factor must NOT be used."""
    today = date.today()
    U.EmissionFactor.objects.create(
        tenant=acme, source_type='electricity_grid', scope='scope_2',
        factor=Decimal('0.42'), unit_of_measure='kwh',
        effective_from=today - timedelta(days=400),
        effective_to=today - timedelta(days=30),
        is_active=True,
    )
    f = carbon_svc._resolve_factor(
        acme, 'electricity_grid', 'scope_2', timezone.now(),
    )
    assert f is None, (
        f'Expired factor should not be returned; got {f}.'
    )


def test_resolve_factor_uses_open_ended_factor(acme):
    """An open-ended factor (effective_to=NULL) is always valid."""
    today = date.today()
    U.EmissionFactor.objects.create(
        tenant=acme, source_type='electricity_grid', scope='scope_2',
        factor=Decimal('0.42'), unit_of_measure='kwh',
        effective_from=today - timedelta(days=10),
        effective_to=None,
        is_active=True,
    )
    f = carbon_svc._resolve_factor(
        acme, 'electricity_grid', 'scope_2', timezone.now(),
    )
    assert f is not None
    assert f.factor == Decimal('0.42')
