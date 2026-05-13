"""CTP service tests (17.3)."""
from datetime import date
from decimal import Decimal

import pytest

from apps.sales.services.ctp import compute_ctp


pytestmark = pytest.mark.django_db


@pytest.fixture
def product(tenant_a):
    from apps.plm.models import Product
    return Product.objects.create(tenant=tenant_a, name='Widget', code='WG-001')


def test_ctp_no_routing_returns_zero(tenant_a, product):
    """Without a released routing, CTP cannot compute capacity."""
    r = compute_ctp(
        tenant=tenant_a, product=product,
        shortfall_qty=Decimal('10'),
        target_date=date.today(),
    )
    assert r.capable_qty == Decimal('0')
    assert r.earliest_completion_date is None
    assert 'no released routing' in r.trace['reason']


def test_ctp_with_routing_returns_completion_date(tenant_a, product):
    """With a released routing, CTP returns a non-null completion date."""
    from apps.pps.models import Routing, RoutingOperation, WorkCenter
    wc = WorkCenter.objects.create(tenant=tenant_a, code='WC1', name='Mill')
    routing = Routing.objects.create(
        tenant=tenant_a, product=product, status='released', name='Default',
    )
    RoutingOperation.objects.create(
        tenant=tenant_a, routing=routing, sequence=10,
        work_center=wc, cycle_seconds=60, setup_minutes=30,
    )
    r = compute_ctp(
        tenant=tenant_a, product=product,
        shortfall_qty=Decimal('10'),
        target_date=date.today(),
    )
    assert r.earliest_completion_date is not None
    assert r.capable_qty == Decimal('10')
    assert r.bottleneck_work_center_id == wc.id
