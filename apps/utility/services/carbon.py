"""Sub-module 14.4 - carbon emission services.

Auto-emit pattern: UtilityConsumption.post_save -> CarbonEmission via signal.
recompute_emissions() lets admins re-snapshot all rows after a factor update.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.utility import models


# Map UtilityType.code -> (default scope, default emission source_type)
_SCOPE_MAP = {
    'electricity': ('scope_2', 'electricity_grid'),
    'natural_gas': ('scope_1', 'natural_gas'),
    'fuel_oil': ('scope_1', 'fuel_oil'),
    'diesel': ('scope_1', 'diesel'),
    'steam': ('scope_2', 'steam'),
    'compressed_air': ('scope_2', 'electricity_grid'),
    'water': ('scope_3', 'water'),
}


def _classify_consumption(consumption):
    """Return (scope, source_type) tuple for a UtilityConsumption row."""
    code = (consumption.meter.utility_type.code or '').lower()
    return _SCOPE_MAP.get(code, ('scope_3', 'supply_chain'))


def _resolve_factor(tenant, source_type, scope, when):
    """Find the active EmissionFactor for a (source_type, scope) at ``when``.

    Returns None if no active factor matches; caller should silently skip.
    """
    when_date = when.date() if hasattr(when, 'date') else when
    qs = models.EmissionFactor.all_objects.filter(
        tenant=tenant,
        source_type=source_type,
        scope=scope,
        is_active=True,
        effective_from__lte=when_date,
    ).order_by('-effective_from')
    return qs.first()


def _resolve_period(tenant, when):
    """Find the cost.AccountingPeriod that contains ``when``."""
    from apps.cost.models import AccountingPeriod
    when_date = when.date() if hasattr(when, 'date') else when
    return AccountingPeriod.all_objects.filter(
        tenant=tenant,
        start_date__lte=when_date,
        end_date__gte=when_date,
    ).first()


@transaction.atomic
def emit_for_consumption(consumption):
    """Emit a CarbonEmission row for the given UtilityConsumption.

    Idempotent: returns the existing row when one already references this
    consumption (enforced at the DB layer by the partial unique constraint).
    """
    existing = models.CarbonEmission.all_objects.filter(
        source_consumption=consumption,
    ).first()
    if existing is not None:
        return existing
    scope, source_type = _classify_consumption(consumption)
    factor = _resolve_factor(consumption.tenant, source_type, scope, consumption.period_start)
    if factor is None:
        return None
    period = _resolve_period(consumption.tenant, consumption.period_start)
    if period is None:
        return None
    return models.CarbonEmission.all_objects.create(
        tenant=consumption.tenant,
        period=period,
        scope=scope,
        source_type=source_type,
        source_quantity=consumption.consumption or Decimal('0'),
        factor=factor,
        source_consumption=consumption,
        recorded_at=timezone.now(),
    )


@transaction.atomic
def recompute_emissions(period):
    """Idempotently rebuild every CarbonEmission row in the period.

    Strategy: delete carbon rows linked to consumptions in this period, then
    re-emit. Manual rows (no source_consumption FK) are left untouched.
    """
    from apps.utility import models as m
    consumptions = m.UtilityConsumption.all_objects.filter(
        tenant=period.tenant,
        period_start__date__gte=period.start_date,
        period_end__date__lte=period.end_date,
        is_reversal=False,
    )
    cons_ids = list(consumptions.values_list('id', flat=True))
    m.CarbonEmission.all_objects.filter(
        source_consumption_id__in=cons_ids,
    ).delete()
    emitted = 0
    for c in consumptions:
        if emit_for_consumption(c):
            emitted += 1
    return {'emitted': emitted, 'consumptions_scanned': len(cons_ids)}


@transaction.atomic
def generate_sustainability_kpi(period, *, generated_by=None):
    """Aggregate emissions + consumption + production into a SustainabilityKPI.

    Idempotent — overwrites the existing row for the (tenant, period) pair.
    """
    from apps.mes.models import ProductionReport
    em_qs = models.CarbonEmission.all_objects.filter(
        tenant=period.tenant, period=period, is_reversal=False,
    )
    s1 = em_qs.filter(scope='scope_1').aggregate(t=Sum('co2e_kg')).get('t') or Decimal('0')
    s2 = em_qs.filter(scope='scope_2').aggregate(t=Sum('co2e_kg')).get('t') or Decimal('0')
    s3 = em_qs.filter(scope='scope_3').aggregate(t=Sum('co2e_kg')).get('t') or Decimal('0')

    cons_qs = models.UtilityConsumption.all_objects.filter(
        tenant=period.tenant,
        period_start__date__gte=period.start_date,
        period_end__date__lte=period.end_date,
        is_reversal=False,
    )
    kwh = cons_qs.filter(meter__utility_type__unit_of_measure='kwh').aggregate(t=Sum('consumption')).get('t') or Decimal('0')
    water = cons_qs.filter(
        meter__utility_type__code__iexact='water',
    ).aggregate(t=Sum('consumption')).get('t') or Decimal('0')
    gas = cons_qs.filter(
        meter__utility_type__code__iexact='natural_gas',
    ).aggregate(t=Sum('consumption')).get('t') or Decimal('0')

    units = ProductionReport.all_objects.filter(
        tenant=period.tenant,
        reported_at__date__gte=period.start_date,
        reported_at__date__lte=period.end_date,
    ).aggregate(t=Sum('good_qty')).get('t') or Decimal('0')

    obj, _ = models.SustainabilityKPI.all_objects.update_or_create(
        tenant=period.tenant, period=period,
        defaults={
            'total_scope_1_kg': s1,
            'total_scope_2_kg': s2,
            'total_scope_3_kg': s3,
            'total_kwh': kwh,
            'total_water_m3': water,
            'total_gas_m3': gas,
            'total_units_produced': units,
            'generated_at': timezone.now(),
            'generated_by': generated_by,
        },
    )
    return obj
