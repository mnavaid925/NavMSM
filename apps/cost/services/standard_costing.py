"""Standard costing services.

Pure-ish — touches the ORM but does not hold open connections; safe to call
from a request handler or a management command.
"""
from decimal import Decimal

from django.db import transaction


def _safe_get(model, **filters):
    qs = getattr(model, 'all_objects', model.objects)
    return qs.filter(**filters).first()


def recompute_from_bom(version):
    """Populate ``StandardCost`` rows on ``version`` from BOM cost rollups.

    For each finished_good / sub_assembly product on the tenant:
        material  = bom_rollup.material_cost
        labor     = bom_rollup.labor_cost      (or computed from routing minutes)
        overhead  = bom_rollup.overhead_cost
        tooling   = bom_rollup.tooling_cost
        subassy   = 0   (rolled into total via BOM tree)
    Idempotent — overwrites existing rows for the version.
    """
    from apps.bom.models import BillOfMaterials, BOMCostRollup
    from apps.plm.models import Product
    from .. import models as cm

    created = 0
    updated = 0
    skipped = 0
    products = list(Product.all_objects.filter(
        tenant_id=version.tenant_id,
        product_type__in=('finished_good', 'sub_assembly'),
    ))
    for product in products:
        bom = BillOfMaterials.all_objects.filter(
            tenant_id=version.tenant_id, product=product, status='released',
        ).order_by('-released_at', '-id').first()
        if bom is None:
            skipped += 1
            continue
        rollup = BOMCostRollup.all_objects.filter(bom=bom).first()
        if rollup is None:
            skipped += 1
            continue

        existing = cm.StandardCost.all_objects.filter(version=version, product=product).first()
        with transaction.atomic():
            if existing is None:
                cm.StandardCost.all_objects.create(
                    tenant_id=version.tenant_id,
                    version=version,
                    product=product,
                    material_cost=rollup.material_cost or Decimal('0'),
                    labor_cost=rollup.labor_cost or Decimal('0'),
                    overhead_cost=rollup.overhead_cost or Decimal('0'),
                    tooling_cost=rollup.tooling_cost or Decimal('0'),
                    subassembly_cost=Decimal('0'),
                    source='bom_rollup',
                )
                created += 1
            else:
                existing.material_cost = rollup.material_cost or Decimal('0')
                existing.labor_cost = rollup.labor_cost or Decimal('0')
                existing.overhead_cost = rollup.overhead_cost or Decimal('0')
                existing.tooling_cost = rollup.tooling_cost or Decimal('0')
                existing.source = 'bom_rollup'
                existing.save()
                updated += 1
    return {'created': created, 'updated': updated, 'skipped': skipped}


def compare_versions(v1, v2):
    """Return per-product diffs between two ``StandardCostVersion`` rows.

    Both versions must belong to the same tenant. Result shape:
        [{'product_sku': 'X', 'v1_total': 100, 'v2_total': 120, 'delta': 20}, ...]
    Sorted by absolute delta descending.
    """
    from .. import models as cm

    rows1 = {c.product_id: c for c in cm.StandardCost.all_objects.filter(version=v1)}
    rows2 = {c.product_id: c for c in cm.StandardCost.all_objects.filter(version=v2)}
    keys = set(rows1) | set(rows2)
    out = []
    for k in keys:
        r1 = rows1.get(k)
        r2 = rows2.get(k)
        t1 = r1.total_cost if r1 else Decimal('0')
        t2 = r2.total_cost if r2 else Decimal('0')
        product = (r1 or r2).product
        out.append({
            'product_id': product.id,
            'product_sku': product.sku,
            'product_name': product.name,
            'v1_total': t1,
            'v2_total': t2,
            'delta': t2 - t1,
        })
    out.sort(key=lambda r: abs(r['delta']), reverse=True)
    return out
