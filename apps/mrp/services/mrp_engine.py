"""Core MRP engine — gross-to-net calculation with multi-level BOM explosion.

Public entry point::

    run_mrp(calculation, mode='regenerative') -> RunSummary

The engine reads:
    - End-item demand from ``calculation.source_mps.lines`` if present, else
      from ``ForecastResult`` rows in the calculation horizon.
    - Component-level demand by exploding ``BillOfMaterials`` for each end item.
    - On-hand / safety stock / lead-time from ``InventorySnapshot`` per product.
    - Open supply from ``ScheduledReceipt`` rows in the horizon.

The engine writes:
    - ``NetRequirement`` rows (one per product per period in horizon)
    - ``MRPPurchaseRequisition`` rows for purchased items with planned orders

Modes:
    ``regenerative`` — wipes prior NetRequirement rows in horizon, recomputes everything.
    ``net_change``   — v1: behaves identically to ``regenerative`` (delete + recompute).
                       True net-change (diff demand/supply, update changed rows only)
                       is deferred to a future optimisation pass. Until then we MUST
                       delete prior rows or the bulk-create at step 4 violates the
                       (mrp_calculation, product, period_start) unique constraint.
    ``simulation``   — same as regenerative but the calling view is expected to
                       gate the apply step. The engine itself is mode-agnostic
                       beyond that.
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from . import lot_sizing


_PR_SEQ_RE = re.compile(r'^MPR-(\d+)$')


def _next_mpr_sequence(tenant):
    """Return the next ``MPR-NNNNN`` number for ``tenant``, computed from the
    largest existing MPR-prefixed value.

    The caller wraps this in a retry-on-IntegrityError loop because two
    concurrent engine runs can both observe the same max value.
    """
    from django.db.models import Max

    from ..models import MRPPurchaseRequisition

    last = (
        MRPPurchaseRequisition.all_objects.filter(
            tenant=tenant, pr_number__startswith='MPR-',
        )
        .aggregate(Max('pr_number'))['pr_number__max']
    )
    n = 1
    if last:
        m = _PR_SEQ_RE.match(str(last))
        if m:
            n = int(m.group(1)) + 1
    return n


@dataclass
class _PeriodBucket:
    period_start: date
    period_end: date
    gross: Decimal = Decimal('0')
    receipts: Decimal = Decimal('0')


@dataclass
class _ProductPlan:
    product_id: int
    bom_level: int = 0
    parent_product_id: int | None = None
    inv_on_hand: Decimal = Decimal('0')
    inv_safety: Decimal = Decimal('0')
    inv_lead_days: int = 7
    inv_lot_method: str = 'l4l'
    inv_lot_value: Decimal = Decimal('0')
    inv_lot_max: Decimal = Decimal('0')
    buckets: dict = field(default_factory=dict)  # period_start -> _PeriodBucket


@dataclass
class RunSummary:
    """Returned by run_mrp(). Caller uses this to populate MRPRunResult."""
    total_planned_orders: int = 0
    total_pr_suggestions: int = 0
    skipped_no_bom: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _bucket_periods(start, end, time_bucket):
    """Yield (period_start, period_end) tuples covering [start, end]."""
    step = timedelta(days=1) if time_bucket == 'day' else timedelta(days=7)
    cur = start
    while cur <= end:
        nxt = cur + step - timedelta(days=1)
        if nxt > end:
            nxt = end
        yield (cur, nxt)
        cur = cur + step


def _period_for(d, period_starts):
    """Snap a date to the corresponding period_start in the horizon."""
    last = None
    for ps in period_starts:
        if d < ps:
            return last or period_starts[0]
        last = ps
    return last or (period_starts[0] if period_starts else d)


def run_mrp(calculation, mode='regenerative'):  # noqa: C901 — algorithm clarity over decomposition
    """Execute the MRP engine against the given MRPCalculation.

    Returns a :class:`RunSummary` describing what the run produced. Persists
    ``NetRequirement`` and ``MRPPurchaseRequisition`` rows inside its own
    transaction-scoped writes (caller wraps in transaction.atomic if needed).
    """
    # Local imports to keep this module ORM-independent at import time.
    from django.db import transaction

    from apps.bom.models import BillOfMaterials
    from apps.plm.models import Product

    from ..models import (
        ForecastResult, ForecastRun, InventorySnapshot, MRPCalculation,
        MRPPurchaseRequisition, NetRequirement, ScheduledReceipt,
    )

    summary = RunSummary()
    tenant = calculation.tenant
    horizon_start = calculation.horizon_start
    horizon_end = calculation.horizon_end
    bucket_kind = calculation.time_bucket

    periods = list(_bucket_periods(horizon_start, horizon_end, bucket_kind))
    if not periods:
        summary.notes.append('No periods in horizon — nothing to compute.')
        return summary
    period_starts = [p[0] for p in periods]

    # ------------------------------------------------------------------
    # 1. Collect end-item demand
    # ------------------------------------------------------------------
    plans: dict[int, _ProductPlan] = {}

    def _ensure(product_id, level=0, parent_id=None):
        plan = plans.get(product_id)
        if plan is None:
            plan = _ProductPlan(
                product_id=product_id, bom_level=level, parent_product_id=parent_id,
            )
            plan.buckets = {ps: _PeriodBucket(ps, pe) for ps, pe in periods}
            plans[product_id] = plan
        else:
            plan.bom_level = min(plan.bom_level, level)
        return plan

    if calculation.source_mps_id is not None:
        # End-item demand from MPS lines
        for line in calculation.source_mps.lines.filter(
            period_start__lte=horizon_end, period_end__gte=horizon_start,
        ).select_related('product'):
            plan = _ensure(line.product_id, level=0, parent_id=None)
            ps = _period_for(line.period_start, period_starts)
            qty = line.firm_planned_qty or line.forecast_qty or Decimal('0')
            plan.buckets[ps].gross += qty
    else:
        # End-item demand from latest completed ForecastRun
        latest = (
            ForecastRun.objects.filter(tenant=tenant, status='completed')
            .order_by('-finished_at').first()
        )
        if latest:
            for r in latest.results.filter(
                period_start__lte=horizon_end, period_end__gte=horizon_start,
            ).select_related('product'):
                plan = _ensure(r.product_id, level=0, parent_id=None)
                ps = _period_for(r.period_start, period_starts)
                plan.buckets[ps].gross += r.forecasted_qty

    # ------------------------------------------------------------------
    # 2. Explode BOMs to compute dependent demand at each level
    # ------------------------------------------------------------------
    end_item_plans = list(plans.values())
    # F-09 (D-09): pre-fetch all released default BOMs in a single query and
    # resolve in Python. Saves up to two DB round-trips per end item and
    # collapses the loop's query budget from 2N to 1.
    end_item_ids = [p.product_id for p in end_item_plans]
    bom_pool = list(
        BillOfMaterials.objects.filter(
            tenant=tenant, product_id__in=end_item_ids,
            status='released', is_default=True,
        )
    )
    bom_by_product = {}
    for b in bom_pool:
        existing = bom_by_product.get(b.product_id)
        # Prefer MBOM over any other type for a given product.
        if existing is None or (b.bom_type == 'mbom' and existing.bom_type != 'mbom'):
            bom_by_product[b.product_id] = b

    end_items_without_bom = [
        p.product_id for p in end_item_plans if p.product_id not in bom_by_product
    ]
    if end_items_without_bom:
        for product in Product.objects.filter(pk__in=end_items_without_bom):
            summary.skipped_no_bom.append(product.sku)

    for end_plan in end_item_plans:
        bom = bom_by_product.get(end_plan.product_id)
        if bom is None:
            continue
        for level, line, expanded_qty in bom.explode():
            comp_plan = _ensure(line.component_id, level=level + 1, parent_id=end_plan.product_id)
            for ps, bucket in end_plan.buckets.items():
                if bucket.gross > 0:
                    comp_plan.buckets[ps].gross += bucket.gross * expanded_qty

    if not plans:
        summary.notes.append('No demand or BOM components in horizon.')
        return summary

    # ------------------------------------------------------------------
    # 3. Layer in inventory snapshots + scheduled receipts
    # ------------------------------------------------------------------
    snap_map = {
        s.product_id: s for s in InventorySnapshot.objects.filter(
            tenant=tenant, product_id__in=plans.keys(),
        )
    }
    for pid, plan in plans.items():
        snap = snap_map.get(pid)
        if snap:
            plan.inv_on_hand = snap.on_hand_qty
            plan.inv_safety = snap.safety_stock
            plan.inv_lead_days = snap.lead_time_days
            plan.inv_lot_method = snap.lot_size_method
            plan.inv_lot_value = snap.lot_size_value
            plan.inv_lot_max = snap.lot_size_max

    for rcp in ScheduledReceipt.objects.filter(
        tenant=tenant, product_id__in=plans.keys(),
        expected_date__gte=horizon_start, expected_date__lte=horizon_end,
    ):
        plan = plans.get(rcp.product_id)
        if plan is None:
            continue
        ps = _period_for(rcp.expected_date, period_starts)
        plan.buckets[ps].receipts += rcp.quantity

    # ------------------------------------------------------------------
    # 4. Gross-to-net + lot sizing → NetRequirement rows
    # ------------------------------------------------------------------
    with transaction.atomic():
        # F-02 (D-02): all three modes wipe and recompute prior rows. True
        # incremental net-change (diff and update-in-place) is deferred until
        # we have a real benchmark of where the time goes; until then any
        # branch that skipped this delete violated the unique_together below.
        NetRequirement.all_objects.filter(mrp_calculation=calculation).delete()
        MRPPurchaseRequisition.all_objects.filter(
            mrp_calculation=calculation,
        ).filter(status='draft').delete()

        net_rows = []
        pr_rows_data = []
        # Walk plans in BOM-level order so end items are written before components
        ordered_plans = sorted(plans.values(), key=lambda p: (p.bom_level, p.product_id))
        for plan in ordered_plans:
            running_oh = plan.inv_on_hand
            net_per_period = []
            for ps, _ in periods:
                bucket = plan.buckets[ps]
                projected = running_oh + bucket.receipts - bucket.gross
                net = Decimal('0')
                if projected < plan.inv_safety:
                    net = plan.inv_safety - projected
                net_per_period.append((ps, bucket, projected, net))
                # net req gets covered by a planned order so on-hand floors at safety stock
                running_oh = max(projected + net, plan.inv_safety) if (bucket.gross > 0 or bucket.receipts > 0 or net > 0) else projected

            planned = lot_sizing.apply(
                plan.inv_lot_method,
                [n for _, _, _, n in net_per_period],
                lot_size_value=plan.inv_lot_value,
                lot_size_max=plan.inv_lot_max,
            )
            planned_map = dict(planned)

            for idx, (ps, bucket, projected, net) in enumerate(net_per_period):
                planned_qty = planned_map.get(idx, Decimal('0'))
                release_date = ps - timedelta(days=plan.inv_lead_days) if planned_qty > 0 else None
                net_rows.append(NetRequirement(
                    tenant=tenant,
                    mrp_calculation=calculation,
                    product_id=plan.product_id,
                    period_start=ps,
                    period_end=plan.buckets[ps].period_end,
                    bom_level=plan.bom_level,
                    parent_product_id=plan.parent_product_id,
                    gross_requirement=bucket.gross,
                    scheduled_receipts_qty=bucket.receipts,
                    projected_on_hand=projected,
                    net_requirement=net,
                    planned_order_qty=planned_qty,
                    planned_release_date=release_date,
                    lot_size_method=plan.inv_lot_method,
                ))
                if planned_qty > 0:
                    summary.total_planned_orders += 1
                    pr_rows_data.append({
                        'product_id': plan.product_id,
                        'bom_level': plan.bom_level,
                        'quantity': planned_qty,
                        'required_by': ps,
                        'release': release_date or ps,
                    })

        if net_rows:
            NetRequirement.all_objects.bulk_create(net_rows, batch_size=500)

        # ------------------------------------------------------------------
        # 5. Auto-generate Purchase Requisitions for purchased items
        # ------------------------------------------------------------------
        # Purchased = product_type in ('raw_material', 'component')
        purchased_ids = set(
            Product.objects.filter(
                tenant=tenant,
                pk__in=[r['product_id'] for r in pr_rows_data],
                product_type__in=('raw_material', 'component'),
            ).values_list('pk', flat=True)
        )

        if purchased_ids:
            from django.db import IntegrityError

            seq = _next_mpr_sequence(tenant)
            for row in pr_rows_data:
                if row['product_id'] not in purchased_ids:
                    continue
                # F-04 (D-04): retry on duplicate pr_number — concurrent engine
                # runs on the same tenant can both observe the same starting
                # sequence value and collide on unique_together(tenant, pr_number).
                created = False
                for attempt in range(5):
                    try:
                        with transaction.atomic():
                            MRPPurchaseRequisition.all_objects.create(
                                tenant=tenant,
                                pr_number=f'MPR-{seq:05d}',
                                mrp_calculation=calculation,
                                product_id=row['product_id'],
                                quantity=row['quantity'],
                                required_by_date=row['required_by'],
                                suggested_release_date=row['release'],
                                status='draft',
                                priority='normal',
                            )
                        created = True
                        seq += 1
                        break
                    except IntegrityError:
                        seq = _next_mpr_sequence(tenant)
                        continue
                if not created:
                    summary.notes.append(
                        f'Could not allocate PR number after 5 attempts for product {row["product_id"]}.'
                    )
                    continue
                summary.total_pr_suggestions += 1

    return summary
