"""Safe ad-hoc report executor.

Builds a Django ORM ``QuerySet`` from a ``ReportDefinition`` + its child
``ReportField`` / ``ReportFilter`` rows, validated against the static
``REGISTERED_SOURCES`` whitelist. Never builds raw SQL. Always scopes to
``request.tenant`` via the model's auto-filter manager.
"""
from __future__ import annotations

import csv
import io
import time
from decimal import Decimal

from django.apps import apps as django_apps
from django.db.models import Sum, Avg, Count, Min, Max, Q
from django.utils import timezone

from .registry import REGISTERED_SOURCES, assert_field_allowed


_AGG_MAP = {
    'sum': Sum,
    'avg': Avg,
    'count': Count,
    'min': Min,
    'max': Max,
}

_OP_MAP = {
    'eq': '',
    'ne': '',
    'gt': '__gt',
    'gte': '__gte',
    'lt': '__lt',
    'lte': '__lte',
    'contains': '__icontains',
    'startswith': '__istartswith',
    'endswith': '__iendswith',
    'in': '__in',
    'isnull': '__isnull',
}


def _resolve_model(label):
    """Look up the Django model from an `app_label.ModelName` string."""
    app_label, _, model_name = label.partition('.')
    return django_apps.get_model(app_label, model_name)


def _coerce_value(operator, value, value_to):
    """Coerce form-text values to the right shape for ORM lookups."""
    if operator == 'in':
        return [v.strip() for v in value.split(',') if v.strip()]
    if operator == 'between':
        return (value, value_to)
    if operator == 'isnull':
        return value.lower() in ('1', 'true', 'yes', 'y')
    return value


def _apply_filter(qs, filter_row):
    """Apply one ReportFilter row to a queryset, validating the field name."""
    field = filter_row.field_name
    op = filter_row.operator
    val = _coerce_value(op, filter_row.value, filter_row.value_to)

    if op == 'ne':
        return qs.exclude(**{field: val})
    if op == 'between':
        lo, hi = val
        return qs.filter(**{f'{field}__gte': lo, f'{field}__lte': hi})
    suffix = _OP_MAP.get(op, '')
    return qs.filter(**{f'{field}{suffix}': val})


def execute_report(report, tenant, parameters=None, limit_override=None):
    """Build + execute the report. Returns ``(rows, row_count, duration_ms)``.

    ``rows`` is a list of OrderedDict-shaped dicts (one per row).
    """
    parameters = parameters or {}
    source = REGISTERED_SOURCES.get(report.data_source.code)
    if source is None:
        raise ValueError(f'Unknown data source: {report.data_source.code!r}')

    # Build the field set first - this also acts as the whitelist check.
    field_rows = list(report.fields.order_by('position', 'id'))
    if not field_rows:
        raise ValueError('Report has no fields configured.')
    for fr in field_rows:
        assert_field_allowed(report.data_source.code, fr.field_name)

    filter_rows = list(report.filters.order_by('position', 'id'))
    for fr in filter_rows:
        assert_field_allowed(report.data_source.code, fr.field_name)

    if report.group_by_field:
        assert_field_allowed(report.data_source.code, report.group_by_field)

    if report.sort_field:
        assert_field_allowed(report.data_source.code, report.sort_field)

    Model = _resolve_model(source['model_label'])
    if not hasattr(Model, 'all_objects'):
        # Non-tenant-aware model - fall back to default manager.
        qs = Model.objects.all()
    else:
        qs = Model.all_objects.filter(tenant=tenant)

    for filter_row in filter_rows:
        qs = _apply_filter(qs, filter_row)

    # Aggregations
    annotate_kwargs = {}
    value_fields = []
    for fr in field_rows:
        if fr.aggregation == 'none':
            value_fields.append(fr.field_name)
        else:
            agg_cls = _AGG_MAP[fr.aggregation]
            alias = f'{fr.field_name.replace("__", "_")}_{fr.aggregation}'
            annotate_kwargs[alias] = agg_cls(fr.field_name)

    started = time.monotonic()
    if report.group_by_field:
        qs = qs.values(report.group_by_field, *value_fields).annotate(**annotate_kwargs)
    elif annotate_kwargs and not value_fields:
        # Pure aggregation - one summary row
        agg = qs.aggregate(**annotate_kwargs)
        return [agg], 1, int((time.monotonic() - started) * 1000)
    else:
        qs = qs.values(*value_fields, *annotate_kwargs.keys())
        if annotate_kwargs:
            qs = qs.annotate(**annotate_kwargs)

    if report.sort_field:
        sign = '-' if report.sort_direction == 'desc' else ''
        qs = qs.order_by(f'{sign}{report.sort_field}')

    limit = limit_override or report.row_limit or 1000
    rows = list(qs[:limit])
    duration_ms = int((time.monotonic() - started) * 1000)
    return rows, len(rows), duration_ms


def rows_to_csv(rows, field_rows=None):
    """Render rows to a CSV string. ``field_rows`` lets us preserve column order
    and use the human-readable display names; if omitted, keys are used."""
    buf = io.StringIO()
    if not rows:
        return ''

    if field_rows:
        headers = [fr.display_name or fr.field_name for fr in field_rows]
        keys = [fr.field_name if fr.aggregation == 'none'
                else f'{fr.field_name.replace("__", "_")}_{fr.aggregation}'
                for fr in field_rows]
    else:
        keys = list(rows[0].keys())
        headers = keys[:]

    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_csv_cell(row.get(k)) for k in keys])
    return buf.getvalue()


def _csv_cell(value):
    """Coerce one cell value to a CSV-safe string."""
    if value is None:
        return ''
    if isinstance(value, Decimal):
        return f'{value.normalize():f}' if value == value.to_integral() else str(value)
    return str(value)


def _jsonify_row(row):
    """Coerce one row dict's Decimal / date / datetime / etc. values to JSON-safe."""
    from datetime import date, datetime
    out = {}
    for k, v in row.items():
        if v is None or isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, Decimal):
            out[k] = str(v)
        elif isinstance(v, (date, datetime)):
            out[k] = v.isoformat()
        else:
            out[k] = str(v)
    return out


def run_and_persist(report, tenant, user=None, parameters=None):
    """Convenience: execute the report and record a ReportRun row.

    Returns ``(run, rows, csv_text)``.
    """
    from apps.bi.models import ReportRun
    run = ReportRun(
        tenant=tenant, report=report, run_by=user,
        run_at=timezone.now(), status='running', parameters=parameters or {},
    )
    run.save()
    try:
        rows, count, duration = execute_report(report, tenant, parameters=parameters)
        run.row_count = count
        run.duration_ms = duration
        run.status = 'completed'
        run.result_preview = [_jsonify_row(r) for r in rows[:50]]
        run.save(update_fields=['row_count', 'duration_ms', 'status', 'result_preview'])
        field_rows = list(report.fields.order_by('position', 'id'))
        csv_text = rows_to_csv(rows, field_rows=field_rows)
        return run, rows, csv_text
    except Exception as exc:  # noqa: BLE001
        run.status = 'failed'
        run.error_message = str(exc)[:2000]
        run.save(update_fields=['status', 'error_message'])
        raise
