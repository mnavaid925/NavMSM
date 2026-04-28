"""Dispatch a pps.ProductionOrder onto the shop floor as a MESWorkOrder.

The dispatcher fans out the production order's RoutingOperation rows into
matching MESWorkOrderOperation rows so the floor terminal has one row per
step to start / pause / stop.

Mostly pure: it computes what to write, then commits inside one
``transaction.atomic`` block. Idempotent on a per-(production_order, tenant)
basis so a double-click in the UI never produces duplicate work orders.
"""
from __future__ import annotations

import re
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone


class DispatchError(Exception):
    """Raised when a ProductionOrder cannot be dispatched to the floor."""


_SEQ_RE = re.compile(r'^WO-(\d+)$')


def _next_wo_number(work_order_model, tenant) -> str:
    last = (
        work_order_model.all_objects
        .filter(tenant=tenant)
        .aggregate(Max('wo_number'))['wo_number__max']
    )
    n = 1
    if last:
        m = _SEQ_RE.match(str(last))
        if m:
            n = int(m.group(1)) + 1
        else:
            n = work_order_model.all_objects.filter(tenant=tenant).count() + 1
    return f'WO-{n:05d}'


def dispatch_production_order(production_order, *, dispatched_by=None):
    """Create a MESWorkOrder + per-routing-op MESWorkOrderOperation rows.

    Idempotent: if the production order already has a non-cancelled MES work
    order, return that one and create no new rows. Returns the work order.
    """
    # Late imports keep this module ORM-light when running test stubs.
    from apps.mes.models import MESWorkOrder, MESWorkOrderOperation

    if production_order.status != 'released':
        raise DispatchError(
            'Only released production orders can be dispatched to the shop floor.'
        )
    if production_order.routing_id is None:
        raise DispatchError(
            'Production order has no routing assigned - cannot fan out operations.'
        )

    tenant = production_order.tenant
    existing = (
        MESWorkOrder.all_objects
        .filter(tenant=tenant, production_order=production_order)
        .exclude(status='cancelled')
        .first()
    )
    if existing is not None:
        return existing

    routing_ops = list(
        production_order.routing.operations.select_related('work_center').order_by('sequence')
    )
    if not routing_ops:
        raise DispatchError(
            'Production order routing has no operations - cannot dispatch.'
        )

    with transaction.atomic():
        wo = MESWorkOrder.all_objects.create(
            tenant=tenant,
            wo_number=_next_wo_number(MESWorkOrder, tenant),
            production_order=production_order,
            product=production_order.product,
            quantity_to_build=production_order.quantity,
            status='dispatched',
            priority=production_order.priority,
            dispatched_by=dispatched_by,
            dispatched_at=timezone.now(),
        )
        qty = Decimal(str(production_order.quantity))
        for op in routing_ops:
            planned = op.total_minutes(qty)
            MESWorkOrderOperation.all_objects.create(
                tenant=tenant,
                work_order=wo,
                routing_operation=op,
                sequence=op.sequence,
                operation_name=op.operation_name,
                work_center=op.work_center,
                setup_minutes=op.setup_minutes,
                run_minutes_per_unit=op.run_minutes_per_unit,
                planned_minutes=planned,
                status='pending',
            )
        return wo
