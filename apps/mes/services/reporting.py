"""Production-reporting helpers.

``record_production`` appends a ProductionReport row, bumps the parent
operation's denormalised totals, and rolls up to the parent work order
inside a single ``transaction.atomic`` block.

``rollup_work_order`` is a pure summary helper used by the work-order detail
page so the template can read good / scrap / rework / completion-percent
without writing the rollup to a model.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone


def record_production(
    work_order_operation,
    *,
    good: Decimal,
    scrap: Decimal,
    rework: Decimal,
    scrap_reason: str = '',
    reported_by=None,
    notes: str = '',
):
    """Persist a ProductionReport and roll its quantities up.

    Bumps the parent op's ``total_good_qty / total_scrap_qty / total_rework_qty``
    in the same transaction, then updates the parent MESWorkOrder's
    ``quantity_completed / quantity_scrapped`` from the sum of all its ops.
    """
    from apps.mes.models import (
        MESWorkOrder,
        MESWorkOrderOperation,
        ProductionReport,
    )

    good = Decimal(str(good or 0))
    scrap = Decimal(str(scrap or 0))
    rework = Decimal(str(rework or 0))
    if good < 0 or scrap < 0 or rework < 0:
        raise ValueError('Production quantities cannot be negative.')
    if (good + scrap + rework) <= 0:
        raise ValueError('At least one of good / scrap / rework must be greater than zero.')

    with transaction.atomic():
        report = ProductionReport.all_objects.create(
            tenant=work_order_operation.tenant,
            work_order_operation=work_order_operation,
            good_qty=good,
            scrap_qty=scrap,
            rework_qty=rework,
            scrap_reason=scrap_reason,
            reported_by=reported_by,
            reported_at=timezone.now(),
            notes=notes,
        )

        # Bump op denormalised totals
        op = MESWorkOrderOperation.all_objects.select_related('work_order').get(
            pk=work_order_operation.pk,
        )
        op.total_good_qty = (op.total_good_qty or Decimal('0')) + good
        op.total_scrap_qty = (op.total_scrap_qty or Decimal('0')) + scrap
        op.total_rework_qty = (op.total_rework_qty or Decimal('0')) + rework
        op.save()

        # Roll up parent work order: quantity_completed = sum of all op
        # ``total_good_qty``; quantity_scrapped = sum of all op
        # ``total_scrap_qty``. Bypassing per-op state lets a partial completion
        # still surface progress to the user without prematurely flipping the
        # work order to ``completed``.
        wo = op.work_order
        agg = MESWorkOrderOperation.all_objects.filter(work_order=wo).aggregate(
            good=Sum('total_good_qty'),
            scrap=Sum('total_scrap_qty'),
        )
        wo.quantity_completed = agg['good'] or Decimal('0')
        wo.quantity_scrapped = agg['scrap'] or Decimal('0')
        wo.save()
        return report


def rollup_work_order(work_order) -> dict:
    """Return a quick summary dict for the work-order detail page."""
    from apps.mes.models import MESWorkOrderOperation

    agg = MESWorkOrderOperation.all_objects.filter(work_order=work_order).aggregate(
        good=Sum('total_good_qty'),
        scrap=Sum('total_scrap_qty'),
        rework=Sum('total_rework_qty'),
        actual=Sum('actual_minutes'),
        planned=Sum('planned_minutes'),
    )
    good = agg['good'] or Decimal('0')
    scrap = agg['scrap'] or Decimal('0')
    rework = agg['rework'] or Decimal('0')
    actual = agg['actual'] or Decimal('0')
    planned = agg['planned'] or Decimal('0')
    target = Decimal(str(work_order.quantity_to_build or 0))
    completed_pct = Decimal('0')
    if target > 0:
        completed_pct = (good / target) * Decimal('100')
        if completed_pct > Decimal('100'):
            completed_pct = Decimal('100')
    return {
        'good': good,
        'scrap': scrap,
        'rework': rework,
        'completed_pct': completed_pct.quantize(Decimal('0.01')),
        'hours_actual': (actual / Decimal('60')).quantize(Decimal('0.01')),
        'hours_planned': (planned / Decimal('60')).quantize(Decimal('0.01')),
    }
