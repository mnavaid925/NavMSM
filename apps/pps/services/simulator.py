"""What-if simulation — applies ScenarioChange records to a copy of an MPS
in memory and returns KPI deltas.

The simulator NEVER mutates real MPS, MPSLine, or production-order data.
It clones the relevant rows into plain dicts, applies each change in
sequence, and returns a result payload the caller persists into a
ScenarioResult. This is intentional — what-if must be safe.
"""
from __future__ import annotations

from decimal import Decimal


def _clone_lines(lines):
    """Project an MPSLine queryset into a list of mutable dicts."""
    out = []
    for line in lines:
        out.append({
            'id': line.pk,
            'product_id': line.product_id,
            'period_start': line.period_start,
            'period_end': line.period_end,
            'forecast_qty': Decimal(str(line.forecast_qty)),
            'firm_planned_qty': Decimal(str(line.firm_planned_qty)),
            'scheduled_qty': Decimal(str(line.scheduled_qty)),
            'priority': 'normal',
        })
    return out


def _apply_change(scratch_lines, change):
    """Mutate the in-memory line list for a single ScenarioChange."""
    target = (change.target_ref or '').strip()
    payload = change.payload or {}
    if change.change_type == 'add_order':
        scratch_lines.append({
            'id': None,
            'product_id': payload.get('product_id'),
            'period_start': payload.get('period_start'),
            'period_end': payload.get('period_end'),
            'forecast_qty': Decimal(str(payload.get('forecast_qty', '0'))),
            'firm_planned_qty': Decimal(str(payload.get('firm_planned_qty', '0'))),
            'scheduled_qty': Decimal('0'),
            'priority': payload.get('priority', 'normal'),
        })
        return
    if change.change_type == 'remove_order':
        target_id = _extract_pk(target)
        scratch_lines[:] = [r for r in scratch_lines if r['id'] != target_id]
        return
    if change.change_type == 'change_qty':
        target_id = _extract_pk(target)
        for r in scratch_lines:
            if r['id'] == target_id:
                if 'forecast_qty' in payload:
                    r['forecast_qty'] = Decimal(str(payload['forecast_qty']))
                if 'firm_planned_qty' in payload:
                    r['firm_planned_qty'] = Decimal(str(payload['firm_planned_qty']))
        return
    if change.change_type == 'change_date':
        target_id = _extract_pk(target)
        for r in scratch_lines:
            if r['id'] == target_id:
                if 'period_start' in payload:
                    r['period_start'] = payload['period_start']
                if 'period_end' in payload:
                    r['period_end'] = payload['period_end']
        return
    if change.change_type == 'change_priority':
        target_id = _extract_pk(target)
        for r in scratch_lines:
            if r['id'] == target_id:
                r['priority'] = payload.get('priority', r['priority'])
        return
    if change.change_type == 'shift_resource':
        # Shifts are recorded for narrative — do not mutate quantities.
        return


def _extract_pk(target_ref):
    if ':' in target_ref:
        try:
            return int(target_ref.split(':', 1)[1])
        except ValueError:
            return None
    try:
        return int(target_ref)
    except (TypeError, ValueError):
        return None


def apply_scenario(scenario):
    """Apply all `ScenarioChange` rows for the scenario and return a KPI summary.

    Returns a dict with the keys ScenarioResult expects:
        {
            'on_time_pct': Decimal,
            'total_load_minutes': int,
            'total_idle_minutes': int,
            'bottleneck_count': int,
            'summary_json': dict,
        }
    """
    base_mps = scenario.base_mps
    scratch_lines = _clone_lines(base_mps.lines.select_related('product').all())
    changes = list(scenario.changes.order_by('sequence', 'pk'))
    for change in changes:
        _apply_change(scratch_lines, change)

    total_qty = sum((r['forecast_qty'] for r in scratch_lines), Decimal('0'))
    firm_qty = sum((r['firm_planned_qty'] for r in scratch_lines), Decimal('0'))
    rush_count = sum(1 for r in scratch_lines if r['priority'] in ('high', 'rush'))
    estimated_load_minutes = int(total_qty * Decimal('30'))  # rough default — 30 min per unit
    estimated_capacity_minutes = max(estimated_load_minutes, 1) + 240 * len(scratch_lines)
    idle_minutes = max(0, estimated_capacity_minutes - estimated_load_minutes)
    on_time_pct = (
        Decimal('100')
        if estimated_load_minutes <= estimated_capacity_minutes
        else Decimal('100') * Decimal(str(estimated_capacity_minutes)) / Decimal(str(estimated_load_minutes))
    ).quantize(Decimal('0.01'))
    bottleneck_count = 1 if estimated_load_minutes > estimated_capacity_minutes * 0.95 else 0

    return {
        'on_time_pct': on_time_pct,
        'total_load_minutes': estimated_load_minutes,
        'total_idle_minutes': idle_minutes,
        'bottleneck_count': bottleneck_count,
        'summary_json': {
            'lines_in': len(base_mps.lines.all()),
            'lines_after': len(scratch_lines),
            'total_forecast_qty': str(total_qty),
            'total_firm_planned_qty': str(firm_qty),
            'rush_lines': rush_count,
            'changes_applied': len(changes),
        },
    }
