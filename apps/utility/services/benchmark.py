"""Sub-module 14.5 - benchmarking services.

generate_snapshot is per-plant per-period; compare returns delta % between
two snapshots. tenant=None industry-average snapshots are materialized by a
superuser-only management command (out of scope for v1).
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.utility import models


@transaction.atomic
def generate_snapshot(period, *, plant_label='main_factory', tenant=None,
                      generated_by=None):
    """Aggregate utility / carbon / production data into a BenchmarkSnapshot.

    Idempotent — overwrites the existing row for (tenant, period, plant_label).
    Pass ``tenant=None`` only when materializing the anonymized industry-avg row.
    """
    from apps.mes.models import ProductionReport

    t = tenant if tenant is not None else period.tenant
    cons = models.UtilityConsumption.all_objects.filter(
        tenant=t,
        period_start__date__gte=period.start_date,
        period_end__date__lte=period.end_date,
        is_reversal=False,
    )
    kwh = cons.filter(meter__utility_type__unit_of_measure='kwh').aggregate(t=Sum('consumption')).get('t') or Decimal('0')
    water = cons.filter(meter__utility_type__code__iexact='water').aggregate(t=Sum('consumption')).get('t') or Decimal('0')
    gas = cons.filter(meter__utility_type__code__iexact='natural_gas').aggregate(t=Sum('consumption')).get('t') or Decimal('0')
    cost = cons.aggregate(t=Sum('total_cost')).get('t') or Decimal('0')
    co2e = (
        models.CarbonEmission.all_objects
        .filter(tenant=t, period=period, is_reversal=False)
        .aggregate(t=Sum('co2e_kg')).get('t') or Decimal('0')
    )
    units = ProductionReport.all_objects.filter(
        tenant=t,
        recorded_at__date__gte=period.start_date,
        recorded_at__date__lte=period.end_date,
    ).aggregate(t=Sum('good_qty')).get('t') or Decimal('0')

    obj, _ = models.BenchmarkSnapshot.all_objects.update_or_create(
        tenant=t, period=period, plant_label=plant_label,
        defaults={
            'total_kwh': kwh,
            'total_water_m3': water,
            'total_gas_m3': gas,
            'total_co2e_kg': co2e,
            'total_cost': cost,
            'total_units_produced': units,
            'generated_at': timezone.now(),
            'generated_by': generated_by,
        },
    )
    return obj


def compare(from_snapshot, to_snapshot):
    """Pure: return delta % dict between two snapshots."""
    def _pct(old, new):
        if not old or old == 0:
            return Decimal('0')
        return ((Decimal(new) - Decimal(old)) / Decimal(old) * Decimal('100')).quantize(Decimal('0.01'))

    return {
        'kwh_delta_pct': _pct(from_snapshot.kwh_per_unit, to_snapshot.kwh_per_unit),
        'water_delta_pct': _pct(from_snapshot.water_per_unit, to_snapshot.water_per_unit),
        'co2e_delta_pct': _pct(from_snapshot.co2e_per_unit, to_snapshot.co2e_per_unit),
        'cost_delta_pct': _pct(from_snapshot.cost_per_unit, to_snapshot.cost_per_unit),
    }


@transaction.atomic
def create_comparison(*, comparison_type, from_snapshot, to_snapshot,
                      tenant, generated_by=None, notes=''):
    """Persist a BenchmarkComparison with computed deltas."""
    deltas = compare(from_snapshot, to_snapshot)
    # Winner heuristic: snapshot with the lower kwh/unit + lower co2e/unit
    f_score = (from_snapshot.kwh_per_unit or Decimal('0')) + (from_snapshot.co2e_per_unit or Decimal('0'))
    t_score = (to_snapshot.kwh_per_unit or Decimal('0')) + (to_snapshot.co2e_per_unit or Decimal('0'))
    if t_score < f_score:
        winner = f'{to_snapshot.plant_label} ({to_snapshot.period.name})'
    elif f_score < t_score:
        winner = f'{from_snapshot.plant_label} ({from_snapshot.period.name})'
    else:
        winner = 'tie'
    return models.BenchmarkComparison.all_objects.create(
        tenant=tenant,
        comparison_type=comparison_type,
        from_snapshot=from_snapshot,
        to_snapshot=to_snapshot,
        kwh_delta_pct=deltas['kwh_delta_pct'],
        water_delta_pct=deltas['water_delta_pct'],
        co2e_delta_pct=deltas['co2e_delta_pct'],
        cost_delta_pct=deltas['cost_delta_pct'],
        winner=winner,
        generated_at=timezone.now(),
        generated_by=generated_by,
        notes=notes,
    )
