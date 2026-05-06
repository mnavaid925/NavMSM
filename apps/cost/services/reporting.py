"""Manufacturing financial reports services.

Pure aggregators that scan WIP entries / production reports / overhead
allocations into one COGMReport, per-product GrossMarginReport rows, and
one PlantPnLReport per period.

Idempotent — re-running upserts the report rows.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone


def generate_cogm(period, *, generated_by=None):
    """Compute the period's COGM and upsert a COGMReport row.

    cogm = opening_wip + DM + DL + OH_applied - closing_wip
    """
    from .. import models as cm

    job_qs = cm.JobCost.all_objects.filter(tenant_id=period.tenant_id)

    # Opening WIP: jobs that were open at start of period.
    opening = job_qs.filter(
        opened_at__lt=period.start_date,
    ).aggregate(t=Sum('total_material'))['t'] or Decimal('0')
    opening_l = job_qs.filter(
        opened_at__lt=period.start_date,
    ).aggregate(t=Sum('total_labor'))['t'] or Decimal('0')
    opening_o = job_qs.filter(
        opened_at__lt=period.start_date,
    ).aggregate(t=Sum('total_overhead'))['t'] or Decimal('0')
    opening_wip = (opening + opening_l + opening_o)

    entry_qs = cm.WIPEntry.all_objects.filter(
        tenant_id=period.tenant_id,
        entry_date__date__gte=period.start_date,
        entry_date__date__lte=period.end_date,
        is_reversal=False,
    )
    direct_materials = entry_qs.filter(entry_type='material_issued').aggregate(
        t=Sum('amount'))['t'] or Decimal('0')
    direct_labor = entry_qs.filter(entry_type='labor_applied').aggregate(
        t=Sum('amount'))['t'] or Decimal('0')
    overhead_applied = entry_qs.filter(entry_type='overhead_applied').aggregate(
        t=Sum('amount'))['t'] or Decimal('0')

    # Closing WIP = jobs still open at period end (sum of denorms).
    closing_qs = job_qs.filter(status='open')
    closing_wip = (
        (closing_qs.aggregate(t=Sum('total_material'))['t'] or Decimal('0'))
        + (closing_qs.aggregate(t=Sum('total_labor'))['t'] or Decimal('0'))
        + (closing_qs.aggregate(t=Sum('total_overhead'))['t'] or Decimal('0'))
        - (closing_qs.aggregate(t=Sum('total_completion_credit'))['t'] or Decimal('0'))
    )
    if closing_wip < 0:
        closing_wip = Decimal('0')

    with transaction.atomic():
        report, _ = cm.COGMReport.all_objects.update_or_create(
            tenant_id=period.tenant_id,
            period=period,
            defaults={
                'opening_wip': opening_wip,
                'direct_materials': direct_materials,
                'direct_labor': direct_labor,
                'overhead_applied': overhead_applied,
                'closing_wip': closing_wip,
                'generated_at': timezone.now(),
                'generated_by': generated_by,
            },
        )
    return report


def generate_gross_margin(period):
    """Generate per-product gross-margin rows for the period.

    units_completed = sum of mes.ProductionReport.good_qty whose reported_at
    falls within the period, grouped by product.
    """
    from apps.mes.models import ProductionReport
    from .. import models as cm

    rows = (
        ProductionReport.all_objects.filter(
            tenant_id=period.tenant_id,
            reported_at__date__gte=period.start_date,
            reported_at__date__lte=period.end_date,
        )
        .values('work_order_operation__work_order__production_order__product')
        .annotate(units=Sum('good_qty'))
    )
    created = 0
    updated = 0
    for r in rows:
        product_id = r['work_order_operation__work_order__production_order__product']
        if product_id is None:
            continue
        units = r['units'] or Decimal('0')
        from apps.plm.models import Product
        product = Product.all_objects.filter(pk=product_id).first()
        if product is None:
            continue

        # Resolve standard cost from the active version.
        version = cm.StandardCostVersion.all_objects.filter(
            tenant_id=period.tenant_id, status='active',
        ).order_by('-effective_from').first()
        std_per_unit = Decimal('0')
        if version is not None:
            sc = cm.StandardCost.all_objects.filter(
                version=version, product=product,
            ).first()
            if sc is not None:
                std_per_unit = sc.total_cost or Decimal('0')

        # Actual cost per unit: average across PO ActualCost rows for this product
        # whose computed_at is within the period.
        actuals = cm.ActualCost.all_objects.filter(
            tenant_id=period.tenant_id,
            production_order__product=product,
            as_of_date__gte=period.start_date,
            as_of_date__lte=period.end_date,
        )
        total_actual = Decimal('0')
        total_units_actual = Decimal('0')
        for a in actuals:
            qty = a.production_order.quantity or Decimal('1')
            total_actual += a.total_cost or Decimal('0')
            total_units_actual += qty
        if total_units_actual > 0:
            actual_per_unit = (total_actual / total_units_actual).quantize(Decimal('0.0001'))
        else:
            actual_per_unit = std_per_unit  # fallback

        sale_price = product.standard_sale_price or Decimal('0')

        with transaction.atomic():
            row, was_created = cm.GrossMarginReport.all_objects.update_or_create(
                tenant_id=period.tenant_id,
                period=period, product=product,
                defaults={
                    'units_completed': units,
                    'standard_cost_per_unit': std_per_unit,
                    'actual_cost_per_unit': actual_per_unit,
                    'unit_sale_price': sale_price,
                    'generated_at': timezone.now(),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
    return {'created': created, 'updated': updated}


def generate_plant_pnl(period, *, selling_expense=None, ga_expense=None,
                       unallocated_overhead=None, generated_by=None):
    """Generate / upsert the period's PlantPnLReport.

    Pulls revenue + cogm from existing report rows; SG&A defaults to 0
    unless overridden.
    """
    from .. import models as cm

    cogm_report = cm.COGMReport.all_objects.filter(
        tenant_id=period.tenant_id, period=period,
    ).first()
    cogm = cogm_report.cogm if cogm_report else Decimal('0')

    margins = cm.GrossMarginReport.all_objects.filter(
        tenant_id=period.tenant_id, period=period,
    )
    revenue = margins.aggregate(t=Sum('revenue'))['t'] or Decimal('0')

    with transaction.atomic():
        report, _ = cm.PlantPnLReport.all_objects.update_or_create(
            tenant_id=period.tenant_id,
            period=period,
            defaults={
                'revenue': revenue,
                'cogm': cogm,
                'selling_expense': selling_expense or Decimal('0'),
                'general_admin_expense': ga_expense or Decimal('0'),
                'unallocated_overhead': unallocated_overhead or Decimal('0'),
                'generated_at': timezone.now(),
                'generated_by': generated_by,
            },
        )
    return report
