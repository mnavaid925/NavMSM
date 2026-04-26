"""Idempotent seeder for BOM sample data across existing tenants.

Per CLAUDE.md "Seed Command Rules":
  - Safe to run repeatedly without --flush
  - Skips per-tenant if data already exists
  - Auto-numbered records (BOM-00001) check existence by (tenant, product,
    bom_type, version, revision) before creating, never by raw number
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.bom.models import (
    AlternateMaterial, BillOfMaterials, BOMLine, BOMRevision, BOMSyncLog,
    BOMSyncMap, CostElement, SubstitutionRule,
)
from apps.core.models import Tenant, set_current_tenant
from apps.plm.models import Product


COST_FIXTURES = {
    # SKU -> dict of cost_type -> unit_cost
    'SKU-1001': {'material': '12.50'},
    'SKU-1002': {'material': '4.25'},
    'SKU-2001': {'material': '0.18'},
    'SKU-2002': {'material': '3.40'},
    'SKU-2003': {'material': '85.00', 'labor': '5.00'},
    'SKU-2004': {'material': '12.00'},
    'SKU-2005': {'material': '120.00', 'labor': '8.00'},
    'SKU-3001': {'labor': '15.00', 'overhead': '5.00'},
    'SKU-3002': {'labor': '10.00', 'overhead': '3.00'},
    'SKU-3003': {'labor': '20.00', 'overhead': '7.00'},
    'SKU-4001': {'labor': '40.00', 'overhead': '15.00', 'tooling': '8.00'},
    'SKU-4002': {'labor': '50.00', 'overhead': '18.00', 'tooling': '10.00'},
    'SKU-4003': {'labor': '35.00', 'overhead': '12.00'},
    'SKU-4004': {'labor': '25.00', 'overhead': '8.00'},
    'SKU-4005': {'labor': '30.00', 'overhead': '10.00'},
}


SUBSTITUTION_RULES = [
    ('M3 Bolt — generic source', 'SKU-2001', 'SKU-2002',
     'Any M3 fastener of equivalent grade and length is acceptable for non-critical assemblies.'),
    ('LCD ↔ Display swap (last resort)', 'SKU-2004', 'SKU-2005',
     'Emergency-use only — requires QA review before shipping.'),
]


def _next_bom_number(tenant):
    """Allocate the next BOM-NNNNN for the given tenant."""
    from django.db.models import Max
    import re
    last = BillOfMaterials.objects.filter(tenant=tenant).aggregate(
        Max('bom_number'),
    )['bom_number__max']
    n = 1
    if last:
        m = re.match(r'^BOM-(\d+)$', str(last))
        if m:
            n = int(m.group(1)) + 1
        else:
            n = BillOfMaterials.objects.filter(tenant=tenant).count() + 1
    return f'BOM-{n:05d}'


def _seed_cost_elements(tenant, products_by_sku, stdout):
    created = 0
    for sku, costs in COST_FIXTURES.items():
        product = products_by_sku.get(sku)
        if product is None:
            continue
        for cost_type, unit_cost in costs.items():
            _, was_created = CostElement.objects.get_or_create(
                tenant=tenant, product=product, cost_type=cost_type,
                defaults={
                    'unit_cost': Decimal(unit_cost),
                    'currency': 'USD',
                    'effective_date': date.today() - timedelta(days=30),
                    'source': 'manual',
                },
            )
            if was_created:
                created += 1
    stdout.write(f'  cost elements: {created} created')


def _get_or_create_bom(tenant, product, bom_type, version, revision, name, status, is_default, created_by):
    bom = BillOfMaterials.objects.filter(
        tenant=tenant, product=product,
        bom_type=bom_type, version=version, revision=revision,
    ).first()
    if bom is not None:
        return bom, False
    bom = BillOfMaterials(
        tenant=tenant, product=product, bom_type=bom_type,
        version=version, revision=revision,
        bom_number=_next_bom_number(tenant),
        name=name, status=status, is_default=is_default,
        effective_from=date.today() - timedelta(days=30),
        created_by=created_by,
    )
    if status in ('approved', 'released'):
        bom.approved_by = created_by
        bom.approved_at = timezone.now()
    if status == 'released':
        bom.released_at = timezone.now()
    bom.save()
    return bom, True


def _add_line(bom, component, quantity, sequence, parent=None, is_phantom=False, scrap=Decimal('0')):
    return BOMLine.objects.create(
        tenant=bom.tenant, bom=bom,
        parent_line=parent, sequence=sequence,
        component=component, quantity=Decimal(str(quantity)),
        unit_of_measure=component.unit_of_measure,
        scrap_percent=scrap, is_phantom=is_phantom,
    )


def _seed_boms_for_tenant(tenant, products_by_sku, admin_user, stdout):
    """Build 5 BOMs of mixed type and lines that produce realistic explosions."""
    fixtures = [
        # (product_sku, bom_type, version, revision, name, status, is_default, [(component_sku, qty, phantom?, parent_idx?)])
        ('SKU-4001', 'ebom', 'A', '01', 'Industrial Controller Mk-3 — Engineering BOM', 'released', True, [
            ('SKU-3001', 1, False, None),
            ('SKU-3002', 2, False, None),
            ('SKU-2003', 1, False, None),
            ('SKU-2001', 8, False, None),
            ('SKU-2002', 1, True,  None),  # phantom heat-sink subassembly
            ('SKU-1001', '0.5', False, 4),  # under phantom
        ]),
        ('SKU-4001', 'mbom', 'A', '01', 'Industrial Controller Mk-3 — Manufacturing BOM', 'released', True, [
            ('SKU-3001', 1, False, None),
            ('SKU-3002', 2, False, None),
            ('SKU-2003', 1, False, None),
            ('SKU-2001', 10, False, None),  # MBOM adds extra fasteners (drift vs EBOM!)
            ('SKU-2004', 1, False, None),
        ]),
        ('SKU-4002', 'ebom', 'A', '01', 'Conveyor Drive 1000W — Engineering BOM', 'released', True, [
            ('SKU-3003', 1, False, None),
            ('SKU-2005', 1, False, None),
            ('SKU-2003', 1, False, None),
            ('SKU-2001', 12, False, None),
            ('SKU-1001', '1.5', False, None),
        ]),
        ('SKU-4002', 'sbom', 'A', '01', 'Conveyor Drive 1000W — Service BOM', 'approved', True, [
            ('SKU-2005', 1, False, None),
            ('SKU-2003', 1, False, None),
            ('SKU-2001', 4, False, None),  # service kit subset
        ]),
        ('SKU-4003', 'ebom', 'A', '01', 'Robotic Arm Joint — Engineering BOM', 'draft', True, [
            ('SKU-3001', 1, False, None),
            ('SKU-3003', 1, False, None),
            ('SKU-2002', 2, False, None),
            ('SKU-2001', 16, False, None),
            ('SKU-1001', '2.0', False, None),
        ]),
    ]

    created_count = 0
    for sku, bom_type, version, revision, name, status, is_default, lines in fixtures:
        product = products_by_sku.get(sku)
        if product is None:
            continue
        bom, was_created = _get_or_create_bom(
            tenant, product, bom_type, version, revision, name,
            status, is_default, admin_user,
        )
        if not was_created:
            continue
        created_count += 1
        # Add lines
        line_index_map = {}
        for idx, (comp_sku, qty, phantom, parent_idx) in enumerate(lines):
            comp = products_by_sku.get(comp_sku)
            if comp is None:
                continue
            parent = line_index_map.get(parent_idx) if parent_idx is not None else None
            line = _add_line(
                bom, comp, qty, sequence=(idx + 1) * 10,
                parent=parent, is_phantom=phantom,
                scrap=Decimal('1.5') if comp.product_type == 'raw_material' else Decimal('0'),
            )
            line_index_map[idx] = line
        # Capture an initial revision snapshot for released/approved BOMs.
        if status in ('approved', 'released'):
            BOMRevision.objects.create(
                tenant=tenant, bom=bom,
                version=version, revision=revision,
                revision_type='major',
                change_summary=f'Initial {bom.get_bom_type_display()} release.',
                snapshot_json=bom.snapshot(),
                changed_by=admin_user,
            )
        # Compute the rollup so the dashboard has data.
        bom.compute_rollup(computed_by=admin_user)
    stdout.write(f'  BOMs: {created_count} created (total {BillOfMaterials.objects.filter(tenant=tenant).count()})')


def _seed_alternates_and_rules(tenant, products_by_sku, admin_user, stdout):
    rule_count = 0
    for name, original_sku, sub_sku, condition in SUBSTITUTION_RULES:
        original = products_by_sku.get(original_sku)
        sub = products_by_sku.get(sub_sku)
        if original is None or sub is None:
            continue
        _, was_created = SubstitutionRule.objects.get_or_create(
            tenant=tenant, name=name,
            defaults={
                'description': f'Catalog rule for {tenant.name}.',
                'original_component': original, 'substitute_component': sub,
                'condition_text': condition,
                'requires_approval': True, 'is_active': True,
            },
        )
        if was_created:
            rule_count += 1
    stdout.write(f'  substitution rules: {rule_count} created')

    # Add alternates to a couple of BOM lines.
    alt_count = 0
    boms = BillOfMaterials.objects.filter(tenant=tenant)[:3]
    for bom in boms:
        for line in bom.lines.all()[:2]:
            sub_sku = 'SKU-2002' if line.component.sku != 'SKU-2002' else 'SKU-2001'
            sub_product = products_by_sku.get(sub_sku)
            if sub_product is None or sub_product.pk == line.component_id:
                continue
            _, was_created = AlternateMaterial.objects.get_or_create(
                tenant=tenant, bom_line=line, alternate_component=sub_product,
                defaults={
                    'priority': 1, 'substitution_type': 'approved',
                    'usage_rule': 'Functionally equivalent for this assembly.',
                    'approval_status': random.choice(['approved', 'pending']),
                    'approved_by': admin_user,
                    'approved_at': timezone.now(),
                },
            )
            if was_created:
                alt_count += 1
    stdout.write(f'  alternates: {alt_count} created')


def _seed_sync_maps(tenant, admin_user, stdout):
    """Create EBOM↔MBOM and MBOM↔SBOM mappings; one will read as drift_detected."""
    ebom = BillOfMaterials.objects.filter(
        tenant=tenant, bom_type='ebom', product__sku='SKU-4001',
    ).first()
    mbom = BillOfMaterials.objects.filter(
        tenant=tenant, bom_type='mbom', product__sku='SKU-4001',
    ).first()
    sbom_4002 = BillOfMaterials.objects.filter(
        tenant=tenant, bom_type='sbom', product__sku='SKU-4002',
    ).first()
    ebom_4002 = BillOfMaterials.objects.filter(
        tenant=tenant, bom_type='ebom', product__sku='SKU-4002',
    ).first()

    created = 0
    if ebom and mbom:
        sm, was_created = BOMSyncMap.objects.get_or_create(
            tenant=tenant, source_bom=ebom, target_bom=mbom,
            defaults={
                'sync_status': 'drift_detected',
                'drift_summary': 'Quantity differs: SKU-2001 (EBOM=8 vs MBOM=10); MBOM has extra component SKU-2004.',
                'last_synced_at': timezone.now() - timedelta(days=2),
                'synced_by': admin_user,
            },
        )
        if was_created:
            created += 1
            BOMSyncLog.objects.create(
                tenant=tenant, sync_map=sm, action='drift', actor=admin_user,
                notes='Initial drift between EBOM and MBOM detected during seeding.',
            )
    if ebom_4002 and sbom_4002:
        sm, was_created = BOMSyncMap.objects.get_or_create(
            tenant=tenant, source_bom=ebom_4002, target_bom=sbom_4002,
            defaults={
                'sync_status': 'in_sync',
                'last_synced_at': timezone.now() - timedelta(days=1),
                'synced_by': admin_user,
            },
        )
        if was_created:
            created += 1
            BOMSyncLog.objects.create(
                tenant=tenant, sync_map=sm, action='reconciled', actor=admin_user,
                notes='EBOM-to-SBOM reconciled at seed time.',
            )
    stdout.write(f'  sync maps: {created} created')


class Command(BaseCommand):
    help = 'Seed BOM demo data (BOMs, lines, alternates, costs, sync) per tenant.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush', action='store_true',
            help='Delete existing BOM data for demo tenants before seeding.',
        )

    def handle(self, *args, **options):
        flush = options.get('flush', False)
        random.seed(42)
        tenants = Tenant.objects.filter(is_active=True).exclude(slug='')
        for tenant in tenants:
            self.stdout.write(self.style.HTTP_INFO(f'\n-> {tenant.name} ({tenant.slug})'))
            set_current_tenant(tenant)

            if flush:
                self.stdout.write('  flushing existing BOM data...')
                BOMSyncLog.all_objects.filter(tenant=tenant).delete()
                BOMSyncMap.all_objects.filter(tenant=tenant).delete()
                AlternateMaterial.all_objects.filter(tenant=tenant).delete()
                SubstitutionRule.all_objects.filter(tenant=tenant).delete()
                BOMRevision.all_objects.filter(tenant=tenant).delete()
                BillOfMaterials.all_objects.filter(tenant=tenant).delete()
                CostElement.all_objects.filter(tenant=tenant).delete()

            if BillOfMaterials.objects.filter(tenant=tenant).exists() and not flush:
                self.stdout.write(self.style.WARNING(
                    '  BOM data already exists — skipping. Use --flush to re-seed.',
                ))
                continue

            admin_user = User.objects.filter(
                tenant=tenant, is_tenant_admin=True,
            ).first()
            if admin_user is None:
                self.stdout.write(self.style.WARNING(
                    f'  No tenant admin found for {tenant.slug} — skipping.',
                ))
                continue

            products_by_sku = {p.sku: p for p in Product.objects.filter(tenant=tenant)}
            if not products_by_sku:
                self.stdout.write(self.style.WARNING(
                    f'  No products found for {tenant.slug} — run seed_plm first.',
                ))
                continue

            _seed_cost_elements(tenant, products_by_sku, self.stdout)
            _seed_boms_for_tenant(tenant, products_by_sku, admin_user, self.stdout)
            _seed_alternates_and_rules(tenant, products_by_sku, admin_user, self.stdout)
            _seed_sync_maps(tenant, admin_user, self.stdout)

        set_current_tenant(None)
        self.stdout.write(self.style.SUCCESS('\nBOM seeding complete.'))
        self.stdout.write(self.style.WARNING(
            'Reminder: log in as a tenant admin (e.g. admin_acme / Welcome@123) to see BOM data — '
            'the Django superuser has tenant=None and will see empty pages.',
        ))
