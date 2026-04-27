"""Generate MRPException rows from a completed MRPCalculation.

A pure-ish function (it reads ORM objects and writes ``MRPException`` rows
in bulk). All decisions are local — no network, no external systems.

Exception triggers:
    late_order      — a planned release date falls in the past.
    expedite        — required by-date earlier than (release_date + lead_time).
    defer           — projected_on_hand is well above safety stock with planned orders.
    no_bom          — end-item demand exists but no released BOM was found.
    no_routing      — purchased items have no inventory snapshot (no lead time).
    below_min       — Min-Max method but planned qty < min.
"""
from datetime import date, timedelta
from decimal import Decimal


def generate_exceptions(calculation, skipped_no_bom_skus=None):
    """Walk a completed calculation and bulk-create MRPException rows.

    ``skipped_no_bom_skus`` is the list returned by run_mrp().RunSummary.skipped_no_bom.
    Pass it through so we can synthesize ``no_bom`` exceptions for those rows.
    """
    from django.db import transaction

    from apps.plm.models import Product

    from ..models import (
        InventorySnapshot, MRPException, NetRequirement,
    )

    tenant = calculation.tenant
    today = date.today()
    skipped_no_bom_skus = skipped_no_bom_skus or []

    rows = []
    snap_map = {
        s.product_id: s for s in InventorySnapshot.objects.filter(tenant=tenant)
    }

    nets = list(NetRequirement.objects.filter(
        mrp_calculation=calculation,
    ).select_related('product').order_by('product_id', 'period_start'))

    for nr in nets:
        snap = snap_map.get(nr.product_id)
        if nr.planned_order_qty <= 0:
            continue

        # late_order: planned release in the past
        if nr.planned_release_date and nr.planned_release_date < today:
            rows.append(MRPException(
                tenant=tenant,
                mrp_calculation=calculation,
                product=nr.product,
                exception_type='late_order',
                severity='high' if (today - nr.planned_release_date).days > 7 else 'medium',
                message=(
                    f'Planned release date {nr.planned_release_date} is in the past — '
                    f'order must be expedited or rescheduled.'
                ),
                recommended_action='expedite',
                target_type='none',
                current_date=nr.planned_release_date,
                recommended_date=today,
            ))

        # expedite: lead time longer than the gap from today to required date
        if snap and nr.period_start:
            gap_days = (nr.period_start - today).days
            if gap_days < snap.lead_time_days:
                rows.append(MRPException(
                    tenant=tenant,
                    mrp_calculation=calculation,
                    product=nr.product,
                    exception_type='expedite',
                    severity='high',
                    message=(
                        f'Required by {nr.period_start} but lead time is {snap.lead_time_days} days '
                        f'(only {gap_days} days available).'
                    ),
                    recommended_action='expedite',
                    target_type='none',
                    current_date=today,
                    recommended_date=nr.period_start - timedelta(days=snap.lead_time_days),
                ))

        # below_min: Min-Max method with planned qty below min
        if (
            nr.lot_size_method == 'min_max' and snap
            and snap.lot_size_value > 0 and nr.planned_order_qty < snap.lot_size_value
        ):
            rows.append(MRPException(
                tenant=tenant,
                mrp_calculation=calculation,
                product=nr.product,
                exception_type='below_min',
                severity='low',
                message=(
                    f'Planned qty {nr.planned_order_qty} below Min-Max minimum {snap.lot_size_value}.'
                ),
                recommended_action='manual_review',
                target_type='none',
            ))

    # no_bom — end items skipped during explosion
    if skipped_no_bom_skus:
        skipped_products = Product.objects.filter(
            tenant=tenant, sku__in=skipped_no_bom_skus,
        )
        for product in skipped_products:
            rows.append(MRPException(
                tenant=tenant,
                mrp_calculation=calculation,
                product=product,
                exception_type='no_bom',
                severity='critical',
                message=(
                    f'No released MBOM (or default BOM) for {product.sku} — '
                    f'dependent demand cannot be exploded.'
                ),
                recommended_action='manual_review',
                target_type='none',
            ))

    # no_routing-equivalent: planned production but no inventory snapshot at all
    products_without_snap = {
        nr.product_id for nr in nets if nr.planned_order_qty > 0
    } - set(snap_map.keys())
    if products_without_snap:
        for product in Product.objects.filter(pk__in=products_without_snap):
            rows.append(MRPException(
                tenant=tenant,
                mrp_calculation=calculation,
                product=product,
                exception_type='no_routing',
                severity='medium',
                message=(
                    f'No inventory snapshot for {product.sku} — using zero on-hand and 7-day default lead time.'
                ),
                recommended_action='manual_review',
                target_type='none',
            ))

    if rows:
        with transaction.atomic():
            MRPException.all_objects.bulk_create(rows, batch_size=500)
    return len(rows)
