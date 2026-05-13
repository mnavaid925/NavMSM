"""Data mart refresh service.

A ``DataMart`` carries a ``source_definition`` JSON of the form::

    {
        "model_label": "mes.ProductionReport",
        "group_by": ["operation__work_order__production_order__product__sku"],
        "measures": {
            "good_qty_sum":   {"field": "good_qty",   "agg": "sum"},
            "scrap_qty_sum":  {"field": "scrap_qty",  "agg": "sum"},
            "report_count":   {"field": "id",         "agg": "count"}
        },
        "date_field": "reported_at",
        "lookback_days": 30
    }

``refresh_mart(mart)`` reads this definition, executes the aggregation
scoped to ``mart.tenant``, deletes any prior snapshot's rows for the mart
inside an atomic block, then inserts a fresh ``DataMartSnapshot`` + child
``DataMartRow`` rows.

Field names in ``group_by`` / ``measures`` are accepted directly because
the mart is admin-defined (not user-input); validate at form layer if you
need to expose this to non-admins.
"""
from __future__ import annotations

import time
from datetime import timedelta
from decimal import Decimal

from django.apps import apps as django_apps
from django.db import transaction
from django.db.models import Sum, Avg, Count, Min, Max
from django.utils import timezone


_AGG_MAP = {
    'sum': Sum,
    'avg': Avg,
    'count': Count,
    'min': Min,
    'max': Max,
}


def _resolve_model(label):
    app_label, _, model_name = label.partition('.')
    return django_apps.get_model(app_label, model_name)


@transaction.atomic
def refresh_mart(mart, triggered_by='manual', triggered_by_user=None):
    """Refresh a data mart in one atomic transaction.

    Returns ``(snapshot, row_count, duration_ms)``.
    """
    from apps.bi.models import DataMartRow, DataMartSnapshot

    started = time.monotonic()
    src = mart.source_definition or {}
    model_label = src.get('model_label')
    if not model_label:
        raise ValueError(f'DataMart {mart.mart_number}: source_definition missing model_label.')

    Model = _resolve_model(model_label)
    if hasattr(Model, 'all_objects'):
        qs = Model.all_objects.filter(tenant=mart.tenant)
    else:
        qs = Model.objects.all()

    # Optional date-range filter.
    date_field = src.get('date_field')
    lookback_days = src.get('lookback_days')
    if date_field and lookback_days:
        cutoff = timezone.now() - timedelta(days=int(lookback_days))
        qs = qs.filter(**{f'{date_field}__gte': cutoff})

    group_by = src.get('group_by') or []
    measures = src.get('measures') or {}
    annotate_kwargs = {}
    for alias, spec in measures.items():
        agg_cls = _AGG_MAP.get(spec.get('agg', 'sum'), Sum)
        annotate_kwargs[alias] = agg_cls(spec['field'])

    if group_by:
        rows_qs = qs.values(*group_by).annotate(**annotate_kwargs)
    else:
        # No group_by means one summary row.
        agg = qs.aggregate(**annotate_kwargs)
        rows_qs = [agg]

    # Delete prior rows; PROTECT on snapshot means we cannot delete the prior
    # snapshot until its rows are gone - which is exactly what we do here.
    DataMartRow.all_objects.filter(tenant=mart.tenant, data_mart=mart).delete()

    snap = DataMartSnapshot.all_objects.create(
        tenant=mart.tenant,
        data_mart=mart,
        snapshot_at=timezone.now(),
        triggered_by=triggered_by,
        triggered_by_user=triggered_by_user,
    )

    rows = list(rows_qs)
    bulk_rows = []
    for row in rows:
        dimension_keys = {k: row.get(k) for k in group_by}
        measure_total = Decimal('0')
        for alias in measures.keys():
            v = row.get(alias)
            if v is not None:
                try:
                    measure_total += Decimal(str(v))
                except Exception:  # noqa: BLE001
                    pass
        bulk_rows.append(DataMartRow(
            tenant=mart.tenant,
            data_mart=mart,
            snapshot=snap,
            row_data={k: _jsonify(v) for k, v in row.items()},
            dimension_keys={k: _jsonify(v) for k, v in dimension_keys.items()},
            measure_total=measure_total,
        ))
    if bulk_rows:
        DataMartRow.objects.bulk_create(bulk_rows)

    duration_ms = int((time.monotonic() - started) * 1000)
    snap.row_count = len(bulk_rows)
    snap.duration_ms = duration_ms
    snap.save(update_fields=['row_count', 'duration_ms'])

    mart.last_refreshed_at = snap.snapshot_at
    mart.last_row_count = snap.row_count
    mart.save(update_fields=['last_refreshed_at', 'last_row_count'])

    return snap, snap.row_count, duration_ms


def _jsonify(value):
    """Coerce Decimal / date / datetime to JSON-friendly shapes."""
    from datetime import date, datetime
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
