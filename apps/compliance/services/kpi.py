"""C.4 — EHS KPI service: TRIR, LTIR, near-miss ratio.

OSHA standard rates:

    TRIR = (recordable incidents in period * 200,000) / total hours worked
    LTIR = (lost-time incidents in period * 200,000) / total hours worked

200,000 normalises to 100 full-time-equivalent employees per year (100 FTE * 40 h/wk
* 50 wk/yr).

Recordable = severity in ('medium', 'high', 'critical') — i.e. anything beyond first aid.
Lost-time = severity in ('high', 'critical') — i.e. medical-treatment-with-time-off or worse.

Near-miss ratio = near_miss_count / recordable_count (Heinrich pyramid metric).
A high ratio (e.g. > 30) indicates a healthy reporting culture; a ratio near 0
indicates under-reporting of near-misses (a leading indicator of future serious
incidents).

`hours_worked` is sourced from `apps.labor.AttendanceRecord` if available; falls
back to a tenant-config-derived estimate when labor data is missing so the page
still renders something useful for non-labor-tenants.
"""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.compliance import models as cm


_RECORDABLE = ('medium', 'high', 'critical')
_LOST_TIME = ('high', 'critical')


def _hours_worked_in_period(tenant, start, end) -> Decimal:
    """Sum AttendanceRecord.worked_minutes across the period (converted to hours).

    Falls back to a placeholder of (12 weeks * 40 h * 50 employees) = 24,000
    when labor data is unavailable so the formula still yields a meaningful
    rate. Documented in the dashboard tooltip so operators understand the
    rate is a planning estimate rather than a regulatory submission.

    Field names are pinned to [apps/labor/models.py](../../labor/models.py):
      - `work_date` (not `attendance_date`)
      - `worked_minutes` (not `hours_worked`)
    """
    try:
        from apps.labor.models import AttendanceRecord
    except ImportError:
        return Decimal('24000')
    qs = AttendanceRecord.objects.filter(
        tenant=tenant, work_date__gte=start, work_date__lte=end,
    )
    total_minutes = Decimal('0')
    for row in qs.only('worked_minutes').iterator():
        if row.worked_minutes is not None:
            total_minutes += Decimal(row.worked_minutes)
    if total_minutes <= 0:
        return Decimal('24000')
    return (total_minutes / Decimal('60')).quantize(Decimal('0.01'))


def _count_in_period(tenant, start, end, *, severities=None, type_categories=None):
    qs = cm.IncidentReport.objects.filter(
        tenant=tenant,
        occurred_at__date__gte=start, occurred_at__date__lte=end,
    ).exclude(status='cancelled')
    if severities:
        qs = qs.filter(severity__in=severities)
    if type_categories:
        qs = qs.filter(incident_type__category__in=type_categories)
    return qs.count()


def compute_ehs_kpis(tenant, *, period_days: int = 90) -> dict:
    """Returns the EHS KPI dict consumed by `IndexView` and the dashboard.

    Structure:
        {
            'period_start': date, 'period_end': date,
            'recordable_count': int, 'lost_time_count': int,
            'near_miss_count': int,
            'hours_worked': Decimal,
            'trir': Decimal (rounded to 2dp), 'ltir': Decimal,
            'near_miss_ratio': Decimal,
            'fallback_hours_used': bool,
        }
    """
    end = timezone.now().date()
    start = end - timedelta(days=period_days)

    recordable = _count_in_period(tenant, start, end, severities=_RECORDABLE)
    lost_time = _count_in_period(tenant, start, end, severities=_LOST_TIME)
    near_miss = cm.IncidentReport.objects.filter(
        tenant=tenant,
        occurred_at__date__gte=start, occurred_at__date__lte=end,
        incident_type__category='near_miss',
    ).exclude(status='cancelled').count()

    hours = _hours_worked_in_period(tenant, start, end)
    fallback_used = hours == Decimal('24000')

    def _rate(numerator):
        if hours <= 0:
            return Decimal('0.00')
        return (Decimal(numerator) * Decimal('200000') / hours).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP,
        )

    if recordable > 0:
        ratio = (Decimal(near_miss) / Decimal(recordable)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP,
        )
    else:
        ratio = Decimal('0.00')

    return {
        'period_start': start,
        'period_end': end,
        'period_days': period_days,
        'recordable_count': recordable,
        'lost_time_count': lost_time,
        'near_miss_count': near_miss,
        'hours_worked': hours,
        'trir': _rate(recordable),
        'ltir': _rate(lost_time),
        'near_miss_ratio': ratio,
        'fallback_hours_used': fallback_used,
    }
