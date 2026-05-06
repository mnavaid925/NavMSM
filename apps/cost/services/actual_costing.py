"""Actual cost rollup + variance analysis services.

Pure-ish: aggregates from inventory.StockMovement, labor.LaborBooking,
cost.OverheadAllocation. Idempotent — re-running overwrites the existing
ActualCost row for the (production_order, as_of_date) key.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone


def compute_actual(production_order, as_of_date=None):
    """Compute actual cost for a production order and upsert an ``ActualCost`` row.

    Returns the created/updated ActualCost instance.
    """
    from apps.labor.models import LaborBooking
    from .. import models as cm

    if as_of_date is None:
        as_of_date = timezone.now().date()

    job = cm.JobCost.all_objects.filter(production_order=production_order).first()

    material = Decimal('0')
    labor = Decimal('0')
    overhead = Decimal('0')

    if job is not None:
        material = job.total_material or Decimal('0')
        labor = job.total_labor or Decimal('0')
        overhead = job.total_overhead or Decimal('0')
    else:
        # Fallback: aggregate directly from labor bookings + overhead allocations
        # tied to the production order's product cost center.
        product = production_order.product
        cc = getattr(product, 'cost_center', None)
        if cc is not None:
            agg = LaborBooking.all_objects.filter(
                tenant_id=production_order.tenant_id, cost_center=cc, kind='direct',
                worked_at__date__lte=as_of_date,
            ).aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
            labor = agg
        oh_agg = cm.OverheadAllocation.all_objects.filter(
            tenant_id=production_order.tenant_id,
            target_production_order=production_order, is_reversed=False,
        ).aggregate(total=Sum('applied_amount'))['total'] or Decimal('0')
        overhead = oh_agg

    with transaction.atomic():
        ac, _ = cm.ActualCost.all_objects.update_or_create(
            tenant_id=production_order.tenant_id,
            production_order=production_order, as_of_date=as_of_date,
            defaults={
                'material_cost': material,
                'labor_cost': labor,
                'overhead_cost': overhead,
                'computed_at': timezone.now(),
            },
        )
    return ac


def compute_variances(production_order, version=None):
    """Compute the 6-axis variance dict for a PO against a standard-cost version.

    Convention: positive = unfavorable; negative = favorable.

    Returns ``None`` if no matching ``StandardCost`` row exists for the
    version+product pair (caller can skip / message to user).
    """
    from .. import models as cm

    if version is None:
        version = cm.StandardCostVersion.all_objects.filter(
            tenant_id=production_order.tenant_id, status='active',
        ).order_by('-effective_from').first()
    if version is None:
        return None

    sc = cm.StandardCost.all_objects.filter(
        version=version, product=production_order.product,
    ).first()
    if sc is None:
        return None

    qty = production_order.quantity or Decimal('1')
    actual = cm.ActualCost.all_objects.filter(
        production_order=production_order,
    ).order_by('-as_of_date').first()
    if actual is None:
        # Compute one on the fly so callers don't need a 2-step recipe.
        actual = compute_actual(production_order)

    std_material = (sc.material_cost or Decimal('0')) * qty
    std_labor = (sc.labor_cost or Decimal('0')) * qty
    std_overhead = ((sc.overhead_cost or Decimal('0')) + (sc.tooling_cost or Decimal('0'))) * qty

    actual_material = actual.material_cost or Decimal('0')
    actual_labor = actual.labor_cost or Decimal('0')
    actual_overhead = actual.overhead_cost or Decimal('0')

    # 60/40 split between price/usage and rate/efficiency is a heuristic for v1
    # (full variance math requires per-component qty + per-op minutes which we
    # do not yet track on actuals). Documented in module section of README.
    mat_total = actual_material - std_material
    lab_total = actual_labor - std_labor
    oh_total = actual_overhead - std_overhead

    return {
        'material_price_variance': (mat_total * Decimal('0.6')).quantize(Decimal('0.01')),
        'material_usage_variance': (mat_total * Decimal('0.4')).quantize(Decimal('0.01')),
        'labor_rate_variance': (lab_total * Decimal('0.6')).quantize(Decimal('0.01')),
        'labor_efficiency_variance': (lab_total * Decimal('0.4')).quantize(Decimal('0.01')),
        'overhead_spending_variance': (oh_total * Decimal('0.5')).quantize(Decimal('0.01')),
        'overhead_volume_variance': (oh_total * Decimal('0.5')).quantize(Decimal('0.01')),
    }
