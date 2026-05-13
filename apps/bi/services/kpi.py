"""KPI calculators + dispatch registry.

Each calculator returns a tuple ``(value, sample_size)`` where ``value`` is a
``Decimal`` and ``sample_size`` is the number of underlying rows used in the
aggregation. Calculators NEVER write to the database - they only read; the
caller is responsible for persisting a ``KPISnapshot`` row.

Adding a KPI:

    1. Add a function ``compute_<code>_kpi(tenant, period_start, period_end,
       scope_type, scope_pk)`` below.
    2. Register it in ``KPI_REGISTRY`` at the bottom of the module.
    3. Add the matching ``KPIDefinition.code`` enum value in models.py.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Tuple

from django.db.models import Q, Sum, Avg, Count


ZERO = Decimal('0')


def _to_decimal(value) -> Decimal:
    """Coerce None / float / int / Decimal to Decimal."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _scope_filter(model_qs, scope_type: str, scope_pk: Optional[int], field_map: dict):
    """Apply a scope filter to a queryset using a field-name lookup map.

    ``field_map`` is e.g. ``{'product': 'operation__work_order__production_order__product_id'}``.
    """
    if scope_type == 'tenant' or scope_pk is None:
        return model_qs
    field = field_map.get(scope_type)
    if field is None:
        return model_qs
    return model_qs.filter(**{field: scope_pk})


# ---------------------------------------------------------------------------
# KPI calculators
# ---------------------------------------------------------------------------

def compute_oee_kpi(tenant, period_start, period_end, scope_type='tenant', scope_pk=None) -> Tuple[Decimal, int]:
    """Mean OEE % over the period, weighted by run_minutes.

    Source: ``iot.OEEPeriod``.
    """
    from apps.iot.models import OEEPeriod
    qs = OEEPeriod.all_objects.filter(
        tenant=tenant, period_date__gte=period_start, period_date__lte=period_end,
    )
    qs = _scope_filter(qs, scope_type, scope_pk, {'asset': 'asset_id'})
    agg = qs.aggregate(weighted=Sum('oee_pct'), n=Count('id'))
    n = agg.get('n') or 0
    if n == 0:
        return ZERO, 0
    total = _to_decimal(agg.get('weighted') or 0)
    return (total / Decimal(n)).quantize(Decimal('0.0001')), n


def compute_throughput_kpi(tenant, period_start, period_end, scope_type='tenant', scope_pk=None) -> Tuple[Decimal, int]:
    """Sum of good_qty over the period.

    Source: ``mes.ProductionReport``.
    """
    from apps.mes.models import ProductionReport
    qs = ProductionReport.all_objects.filter(
        tenant=tenant, reported_at__date__gte=period_start, reported_at__date__lte=period_end,
    )
    qs = _scope_filter(qs, scope_type, scope_pk, {
        'product': 'work_order_operation__work_order__production_order__product_id',
        'asset': 'work_order_operation__work_order__production_order__product_id',
    })
    agg = qs.aggregate(total=Sum('good_qty'), n=Count('id'))
    return _to_decimal(agg.get('total') or 0), agg.get('n') or 0


def compute_yield_kpi(tenant, period_start, period_end, scope_type='tenant', scope_pk=None) -> Tuple[Decimal, int]:
    """First-pass yield % = good / (good + scrap + rework).

    Source: ``mes.ProductionReport``.
    """
    from apps.mes.models import ProductionReport
    qs = ProductionReport.all_objects.filter(
        tenant=tenant, reported_at__date__gte=period_start, reported_at__date__lte=period_end,
    )
    qs = _scope_filter(qs, scope_type, scope_pk, {
        'product': 'work_order_operation__work_order__production_order__product_id',
    })
    agg = qs.aggregate(
        g=Sum('good_qty'), s=Sum('scrap_qty'), r=Sum('rework_qty'), n=Count('id'),
    )
    good = _to_decimal(agg.get('g') or 0)
    scrap = _to_decimal(agg.get('s') or 0)
    rework = _to_decimal(agg.get('r') or 0)
    denom = good + scrap + rework
    n = agg.get('n') or 0
    if denom == 0:
        return ZERO, n
    return ((good / denom) * Decimal('100')).quantize(Decimal('0.0001')), n


def compute_scrap_rate_kpi(tenant, period_start, period_end, scope_type='tenant', scope_pk=None) -> Tuple[Decimal, int]:
    """Scrap rate % = scrap / (good + scrap + rework).

    Source: ``mes.ProductionReport``.
    """
    from apps.mes.models import ProductionReport
    qs = ProductionReport.all_objects.filter(
        tenant=tenant, reported_at__date__gte=period_start, reported_at__date__lte=period_end,
    )
    qs = _scope_filter(qs, scope_type, scope_pk, {
        'product': 'work_order_operation__work_order__production_order__product_id',
    })
    agg = qs.aggregate(
        g=Sum('good_qty'), s=Sum('scrap_qty'), r=Sum('rework_qty'), n=Count('id'),
    )
    good = _to_decimal(agg.get('g') or 0)
    scrap = _to_decimal(agg.get('s') or 0)
    rework = _to_decimal(agg.get('r') or 0)
    denom = good + scrap + rework
    n = agg.get('n') or 0
    if denom == 0:
        return ZERO, n
    return ((scrap / denom) * Decimal('100')).quantize(Decimal('0.0001')), n


def compute_on_time_delivery_kpi(tenant, period_start, period_end, scope_type='tenant', scope_pk=None) -> Tuple[Decimal, int]:
    """OTD % across all PO receipts in the period.

    Source: ``procurement.SupplierMetricEvent`` (event_type=po_received_*).
    """
    from apps.procurement.models import SupplierMetricEvent
    qs = SupplierMetricEvent.all_objects.filter(
        tenant=tenant,
        posted_at__date__gte=period_start,
        posted_at__date__lte=period_end,
        event_type__startswith='po_received',
    )
    qs = _scope_filter(qs, scope_type, scope_pk, {'supplier': 'supplier_id'})
    total = qs.count()
    if total == 0:
        return ZERO, 0
    on_time = qs.filter(event_type='po_received_on_time').count()
    return ((Decimal(on_time) / Decimal(total)) * Decimal('100')).quantize(Decimal('0.0001')), total


def compute_supplier_otd_kpi(tenant, period_start, period_end, scope_type='tenant', scope_pk=None) -> Tuple[Decimal, int]:
    """Alias for `compute_on_time_delivery_kpi`. Useful in dashboards that
    want a supplier-scoped variant explicitly.
    """
    return compute_on_time_delivery_kpi(tenant, period_start, period_end, scope_type, scope_pk)


def compute_gross_margin_kpi(tenant, period_start, period_end, scope_type='tenant', scope_pk=None) -> Tuple[Decimal, int]:
    """Mean gross-margin % across the period.

    Source: ``cost.GrossMarginReport``.
    """
    try:
        from apps.cost.models import GrossMarginReport
    except ImportError:
        return ZERO, 0
    qs = GrossMarginReport.all_objects.filter(
        tenant=tenant,
        period__start_date__lte=period_end,
        period__end_date__gte=period_start,
    )
    qs = _scope_filter(qs, scope_type, scope_pk, {'product': 'product_id'})
    agg = qs.aggregate(avg=Avg('margin_percent'), n=Count('id'))
    return _to_decimal(agg.get('avg') or 0).quantize(Decimal('0.0001')), agg.get('n') or 0


def compute_energy_intensity_kpi(tenant, period_start, period_end, scope_type='tenant', scope_pk=None) -> Tuple[Decimal, int]:
    """kWh per unit produced.

    Sources: ``utility.UtilityConsumption`` for kWh, ``mes.ProductionReport``
    for good_qty.
    """
    try:
        from apps.utility.models import UtilityConsumption
    except ImportError:
        return ZERO, 0
    from apps.mes.models import ProductionReport
    consumption_qs = UtilityConsumption.all_objects.filter(
        tenant=tenant,
        period_start__lte=period_end,
        period_end__gte=period_start,
        meter__utility_type__code='electricity',
    )
    consumption_total = _to_decimal(
        consumption_qs.aggregate(t=Sum('consumption')).get('t') or 0
    )
    prod_qs = ProductionReport.all_objects.filter(
        tenant=tenant, reported_at__date__gte=period_start, reported_at__date__lte=period_end,
    )
    units = _to_decimal(prod_qs.aggregate(t=Sum('good_qty')).get('t') or 0)
    n = consumption_qs.count() + prod_qs.count()
    if units == 0:
        return ZERO, n
    return (consumption_total / units).quantize(Decimal('0.0001')), n


def compute_carbon_intensity_kpi(tenant, period_start, period_end, scope_type='tenant', scope_pk=None) -> Tuple[Decimal, int]:
    """kgCO2e per unit produced.

    Sources: ``utility.CarbonEmission`` for kgCO2e, ``mes.ProductionReport``
    for good_qty.
    """
    try:
        from apps.utility.models import CarbonEmission
    except ImportError:
        return ZERO, 0
    from apps.mes.models import ProductionReport
    emission_qs = CarbonEmission.all_objects.filter(
        tenant=tenant,
        recorded_at__date__gte=period_start,
        recorded_at__date__lte=period_end,
    )
    emission_total = _to_decimal(
        emission_qs.aggregate(t=Sum('co2e_kg')).get('t') or 0
    )
    prod_qs = ProductionReport.all_objects.filter(
        tenant=tenant, reported_at__date__gte=period_start, reported_at__date__lte=period_end,
    )
    units = _to_decimal(prod_qs.aggregate(t=Sum('good_qty')).get('t') or 0)
    n = emission_qs.count() + prod_qs.count()
    if units == 0:
        return ZERO, n
    return (emission_total / units).quantize(Decimal('0.0001')), n


# ---------------------------------------------------------------------------
# Dispatch registry
# ---------------------------------------------------------------------------

KPI_REGISTRY = {
    'oee': compute_oee_kpi,
    'throughput': compute_throughput_kpi,
    'yield': compute_yield_kpi,
    'scrap_rate': compute_scrap_rate_kpi,
    'on_time_delivery': compute_on_time_delivery_kpi,
    'supplier_otd': compute_supplier_otd_kpi,
    'gross_margin': compute_gross_margin_kpi,
    'energy_intensity': compute_energy_intensity_kpi,
    'carbon_intensity': compute_carbon_intensity_kpi,
}


def dispatch_kpi(code, tenant, period_start, period_end, scope_type='tenant', scope_pk=None):
    """Look up and call the calculator for ``code``. Returns (Decimal, int)."""
    calc = KPI_REGISTRY.get(code)
    if calc is None:
        raise ValueError(f'Unknown KPI code: {code!r}')
    return calc(tenant, period_start, period_end, scope_type, scope_pk)


def classify_value(definition, value: Decimal) -> str:
    """Map a Decimal value to a 'on_target' / 'warning' / 'critical' label.

    Uses ``KPIDefinition.direction`` so "higher is better" KPIs trip when
    value falls BELOW the warning/critical thresholds.
    """
    if value is None:
        return 'on_target'
    if definition.warning_threshold is None and definition.critical_threshold is None:
        return 'on_target'
    higher = definition.direction == 'higher_is_better'
    if higher:
        if definition.critical_threshold is not None and value <= definition.critical_threshold:
            return 'critical'
        if definition.warning_threshold is not None and value <= definition.warning_threshold:
            return 'warning'
        return 'on_target'
    # lower-is-better
    if definition.critical_threshold is not None and value >= definition.critical_threshold:
        return 'critical'
    if definition.warning_threshold is not None and value >= definition.warning_threshold:
        return 'warning'
    return 'on_target'


def refresh_snapshot(definition, period_start, period_end, scope_type='tenant', scope_pk=None, scope_label=''):
    """Compute the KPI and upsert a KPISnapshot row. Returns the snapshot.

    Idempotent on ``(tenant, kpi_definition, period_start, scope_type, scope_pk)``.
    """
    from django.utils import timezone
    from apps.bi.models import KPISnapshot
    value, n = dispatch_kpi(
        definition.code, definition.tenant, period_start, period_end, scope_type, scope_pk,
    )
    status = classify_value(definition, value)
    prior, _ = (None, 0)
    snap, created = KPISnapshot.all_objects.get_or_create(
        tenant=definition.tenant,
        kpi_definition=definition,
        period_start=period_start,
        scope_type=scope_type,
        scope_pk=scope_pk,
        defaults=dict(
            period_end=period_end,
            value=value,
            prior_period_value=None,
            status=status,
            sample_size=n,
            computed_at=timezone.now(),
            scope_label=scope_label,
        ),
    )
    if not created:
        snap.period_end = period_end
        snap.prior_period_value = snap.value
        snap.value = value
        snap.status = status
        snap.sample_size = n
        snap.scope_label = scope_label or snap.scope_label
        snap.computed_at = timezone.now()
        snap.save(update_fields=[
            'period_end', 'prior_period_value', 'value', 'status',
            'sample_size', 'scope_label', 'computed_at',
        ])
    return snap
