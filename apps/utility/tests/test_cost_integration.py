"""End-to-end: utility allocation -> cost.DriverActuals -> cost.OverheadAllocation."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.utility import models as U
from apps.utility.services import allocation as alloc_svc


pytestmark = pytest.mark.django_db


def test_post_allocation_creates_cost_driver_actuals(
    acme, acp_open, meter, consumption,
):
    """post_allocation MUST emit a matching cost.DriverActuals row when cost_driver linked."""
    from apps.cost.models import DriverActuals
    from apps.labor.models import CostCenter
    cc = CostCenter.objects.create(tenant=acme, code='CC-UT', name='Utilities')
    targets = [{
        'cost_center': cc, 'product': None, 'production_order': None,
        'share_pct': Decimal('100'),
    }]
    alloc_svc.post_allocation(acp_open, meter, targets)
    da = DriverActuals.all_objects.filter(
        tenant=acme, period=acp_open, cost_center=cc,
        driver=meter.utility_type.cost_driver,
    )
    assert da.count() == 1
    assert da.first().quantity > 0


def test_overhead_apply_sweeps_utility_into_pool(
    acme, acp_open, meter, consumption,
):
    """End-to-end: utility post_allocation -> apply_overhead -> OverheadAllocation."""
    from apps.cost.models import DriverActuals, OverheadPool, OverheadRate, OverheadAllocation
    from apps.cost.services import overhead as oh_svc
    from apps.labor.models import CostCenter

    # 1. Create the Utilities pool wired to the same kWh driver
    pool = OverheadPool.objects.create(
        tenant=acme, code='UTIL', name='Utilities',
        pool_type='variable', default_driver=meter.utility_type.cost_driver,
        allocation_method='abc',
    )
    OverheadRate.objects.create(
        tenant=acme, pool=pool, period=acp_open,
        driver=meter.utility_type.cost_driver,
        budgeted_amount=Decimal('1000'),
        budgeted_driver_qty=Decimal('100'),
    )

    # 2. Post utility allocation -> writes DriverActuals
    cc = CostCenter.objects.create(tenant=acme, code='CC-UT', name='Utilities')
    targets = [{
        'cost_center': cc, 'product': None, 'production_order': None,
        'share_pct': Decimal('100'),
    }]
    alloc_svc.post_allocation(acp_open, meter, targets)
    assert DriverActuals.all_objects.filter(
        tenant=acme, period=acp_open, cost_center=cc,
    ).exists()

    # 3. Run cost.apply_overhead -> creates OverheadAllocation rows
    counts = oh_svc.apply_overhead(acp_open)
    assert counts['allocations'] >= 1
    assert OverheadAllocation.objects.filter(
        tenant=acme, pool=pool, period=acp_open,
    ).exists()


def test_reverse_utility_allocation_clears_cost_driver_actual(
    acme, acp_open, meter, consumption,
):
    from apps.cost.models import DriverActuals
    from apps.labor.models import CostCenter

    cc = CostCenter.objects.create(tenant=acme, code='CC-UT2', name='Utilities')
    targets = [{
        'cost_center': cc, 'product': None, 'production_order': None,
        'share_pct': Decimal('100'),
    }]
    alloc_svc.post_allocation(acp_open, meter, targets)
    a = U.UtilityAllocation.all_objects.filter(tenant=acme).first()
    assert DriverActuals.all_objects.filter(tenant=acme, period=acp_open).count() == 1

    alloc_svc.reverse_allocation(a, reason='wrong split')
    assert DriverActuals.all_objects.filter(tenant=acme, period=acp_open).count() == 0


def test_post_allocation_skips_driver_actual_when_no_cost_driver(
    acme, acp_open, water_meter,
):
    """utility_type without a cost_driver -> no DriverActuals row written."""
    from apps.cost.models import DriverActuals
    from apps.labor.models import CostCenter

    # Add some water consumption inside the period
    period_dt = timezone.make_aware(
        timezone.datetime(
            acp_open.start_date.year,
            acp_open.start_date.month,
            acp_open.start_date.day, 9, 0,
        )
    )
    U.UtilityConsumption.objects.create(
        tenant=acme, meter=water_meter,
        period_start=period_dt,
        period_end=period_dt + timedelta(hours=1),
        start_reading=Decimal('0'), end_reading=Decimal('100'),
        unit_cost=Decimal('0.05'),
    )
    cc = CostCenter.objects.create(tenant=acme, code='CC-WT', name='Water')
    targets = [{
        'cost_center': cc, 'product': None, 'production_order': None,
        'share_pct': Decimal('100'),
    }]
    result = alloc_svc.post_allocation(acp_open, water_meter, targets)
    assert result['created'] == 1
    # water meter's UtilityType has no cost_driver -> no DriverActuals
    assert DriverActuals.all_objects.filter(
        tenant=acme, period=acp_open, cost_center=cc,
    ).count() == 0
