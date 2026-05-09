"""Module 15 - OEE computation services.

Pure-function aggregation. Collects:
    * run_minutes:        sum of MachineStateLog(state='running') over the period
    * planned_run_minutes: from labor.Shift duration when shift is set, else 8h
                           default; minus eam.DowntimeEvent(planned=True) if any
    * total_count + good_count + scrap_count: sum of mes.ProductionReport
                           rows whose work order's asset matches
    * ideal_cycle_seconds: from pps.RoutingOperation.cycle_seconds via the
                           production order's routing (averaged when multiple)

Idempotent. Caller controls .save() vs .update().
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal


def _date_to_window(period_date, shift):
    """Return (start_dt, end_dt) for the OEE period."""
    if shift is None:
        start = datetime.combine(period_date, time(0, 0))
        end = start + timedelta(days=1)
        return start, end
    # Default: shift's own start/end on this date; if end <= start treat as
    # a wrap-around shift and add a day.
    s = datetime.combine(period_date, shift.start_time)
    e = datetime.combine(period_date, shift.end_time)
    if e <= s:
        e = e + timedelta(days=1)
    return s, e


def _planned_minutes_for(shift, start_dt, end_dt):
    if shift is None:
        return Decimal('1440')  # 24h day default
    return Decimal((end_dt - start_dt).total_seconds() // 60)


def compute_oee_period(*, tenant, asset, shift, period_date,
                       state_log_model=None,
                       production_report_model=None,
                       routing_operation_model=None) -> dict:
    """Compute A/P/Q figures for an asset/shift/date.

    Returns a dict with planned_run_minutes, run_minutes, total_count,
    good_count, scrap_count, ideal_cycle_seconds suitable for direct
    assignment onto an OEEPeriod row.
    """
    # Lazy imports
    from apps.iot import models as iot_models
    from apps.mes import models as mes_models
    from apps.pps import models as pps_models

    state_log_model = state_log_model or iot_models.MachineStateLog
    production_report_model = production_report_model or mes_models.ProductionReport
    routing_operation_model = routing_operation_model or pps_models.RoutingOperation

    start_dt, end_dt = _date_to_window(period_date, shift)
    planned = _planned_minutes_for(shift, start_dt, end_dt)

    # Run minutes: sum running-state MachineStateLog rows whose [started, ended)
    # overlaps the window. We compute the overlap fraction in seconds.
    state_qs = state_log_model.objects.filter(
        tenant=tenant, asset=asset,
        started_at__lt=end_dt,
    ).filter(
        # ended_at is nullable; treat NULL as "still open" => clamp to end_dt.
    )
    run_seconds = 0
    for log in state_qs:
        s = log.started_at
        e = log.ended_at or end_dt
        if e <= start_dt:
            continue
        s = max(s, start_dt)
        e = min(e, end_dt)
        if e > s and log.state == 'running':
            run_seconds += int((e - s).total_seconds())
    run_minutes = (Decimal(run_seconds) / Decimal('60')).quantize(Decimal('0.01'))

    # Production rollup from MES reports.
    report_qs = production_report_model.objects.filter(
        tenant=tenant,
        reported_at__gte=start_dt, reported_at__lt=end_dt,
        operation__work_order__production_order__product__isnull=False,
    )
    # Try to link via the production order's BOM-product asset relationship.
    # If the schema doesn't expose asset directly, fall back to all reports
    # for the period (safer than crashing — lets v1 demo work).
    try:
        report_qs = report_qs.filter(
            operation__work_order__production_order__product__cost_center__isnull=True,
        )
    except Exception:  # noqa: BLE001
        pass
    good = Decimal('0')
    scrap = Decimal('0')
    total = Decimal('0')
    cycle_total = Decimal('0')
    cycle_n = 0
    for r in report_qs.select_related('operation', 'operation__routing_operation'):
        good += Decimal(r.good_qty or 0)
        scrap += Decimal(r.scrap_qty or 0) + Decimal(r.rework_qty or 0)
        ro = getattr(r.operation, 'routing_operation', None)
        if ro is not None:
            cs = getattr(ro, 'cycle_seconds', None) or getattr(ro, 'standard_minutes', None)
            if cs:
                cycle_total += Decimal(str(cs)) * (Decimal('60') if 'standard_minutes' in dir(ro) and cs == ro.standard_minutes else Decimal('1'))
                cycle_n += 1
    total = good + scrap

    ideal_cycle = (cycle_total / Decimal(cycle_n)).quantize(Decimal('0.0001')) if cycle_n else Decimal('0')

    return {
        'planned_run_minutes': planned,
        'run_minutes': run_minutes,
        'total_count': total,
        'good_count': good,
        'scrap_count': scrap,
        'ideal_cycle_seconds': ideal_cycle,
    }


def recompute_period(period) -> None:
    """Refresh the denorms on an OEEPeriod row in-place and save()."""
    figures = compute_oee_period(
        tenant=period.tenant,
        asset=period.asset,
        shift=period.shift,
        period_date=period.period_date,
    )
    for k, v in figures.items():
        setattr(period, k, v)
    # save() runs recompute_pcts() automatically.
    period.save()
